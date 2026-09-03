import csv
import time
import threading
import logging
import uuid
import secrets
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.text import slugify
from django.template.loader import render_to_string

from .models import (
    Patient, PatientVisit, PatientDocument,
    PatientAllergy, PatientMedication, Appointment,
    BulkPatientUpload, PatientMerge
)
from .serializers import (
    PatientSerializer, PatientVisitSerializer, PatientDocumentSerializer,
    PatientAllergySerializer, PatientMedicationSerializer, AppointmentSerializer,
    PatientSearchSerializer, AppointmentScheduleSerializer, PatientLoginSerializer,
    BulkPatientUploadSerializer, PatientMergeSerializer,
    PatientPasswordResetRequestSerializer, PatientPasswordResetVerifySerializer,
    PatientPasswordResetConfirmSerializer, PatientPasswordChangeSerializer
)
from tenants.models import TenantUser, Department
from core.views import TenantScopedModelViewSet
from users.models import PasswordResetToken
from users.tasks import send_password_reset_email_task, queue_login_notification
from patients.tasks import send_appointment_email_task
from smartcare_hms.email_delivery import dispatch_email_task
from core.models import AuditLog
from .services import merge_patients, unmerge_patient

logger = logging.getLogger(__name__)


def _write_audit_log_async(payload):
    """Background worker that persists an AuditLog row on its own DB connection.

    Runs in a separate thread so it never blocks or interferes with the API
    request. Failures are logged and swallowed.
    """
    from django.db import close_old_connections
    close_old_connections()
    try:
        AuditLog.objects.create(**payload)
    except Exception:
        logger.exception(
            'Failed to write patient audit log for action=%s',
            payload.get('action') if isinstance(payload, dict) else 'unknown',
        )
    finally:
        close_old_connections()


class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000


def _dispatch_appointment_reminder(appointment, channels=None, preferred_channel=None):
    """
    Send a reminder to the patient using the available contact channels.
    
    Uses the tenant's configured email settings for sending appointment reminders.
    Falls back to global email settings if tenant configuration is incomplete.
    """
    patient = getattr(appointment, 'patient', None)
    if patient is None:
        return {'status': 'skipped', 'channels': []}

    tenant = getattr(appointment, 'tenant', None)
    if tenant is None:
        logger.warning('Appointment %s has no associated tenant', appointment.id)
        return {'status': 'skipped', 'channels': [], 'error': 'No tenant found'}

    normalized_channels = []
    if channels:
        normalized_channels = [channel.lower() for channel in channels if channel]
    if preferred_channel:
        normalized_channels = [preferred_channel.lower()] + [channel for channel in normalized_channels if channel != preferred_channel.lower()]
    if not normalized_channels:
        normalized_channels = ['email'] if patient.email or getattr(appointment.doctor, 'email', None) else ['sms']

    sent_channels = []
    reminder_message = (
        f"Hello {patient.get_full_name()}, this is a reminder that you have an appointment on "
        f"{appointment.scheduled_date} at {appointment.scheduled_time}."
    )

    if 'email' in normalized_channels and patient.email:
        try:
            dispatch_email_task(send_appointment_email_task, args=(appointment.id, 'patient'))
            sent_channels.append('email')
            logger.info('Appointment reminder email sent to patient %s (%s)', patient.id, patient.email)
        except Exception as exc:
            logger.error('Failed to send appointment reminder email to patient %s: %s', patient.id, exc)
            return {
                'status': 'partial',
                'channels': sent_channels,
                'error': 'Appointment saved, but the tenant confirmation email could not be sent. Please check the tenant email settings.',
            }

    doctor = getattr(appointment, 'doctor', None)
    if doctor and doctor.email and 'email' in normalized_channels:
        try:
            dispatch_email_task(send_appointment_email_task, args=(appointment.id, 'doctor'))
            logger.info('Appointment assignment email sent to doctor %s (%s)', doctor.id, doctor.email)
        except Exception as exc:
            logger.error('Failed to send appointment assignment email to doctor %s: %s', doctor.id, exc)
            return {
                'status': 'partial',
                'channels': sent_channels,
                'error': 'Appointment saved, but an appointment email could not be sent. Please check the tenant email settings.',
            }

    if ('sms' in normalized_channels or 'whatsapp' in normalized_channels) and patient.phone:
        logger.info('Appointment reminder queued for patient %s via %s', patient.id, normalized_channels)
        sent_channels.append('sms' if 'sms' in normalized_channels else 'whatsapp')

    if sent_channels:
        appointment.reminder_sent = True
        appointment.reminder_sent_date = timezone.now()
        appointment.save(update_fields=['reminder_sent', 'reminder_sent_date'])
        return {'status': 'sent', 'channels': sent_channels}

    return {'status': 'skipped', 'channels': []}


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def patient_login(request):
    """Allow a patient to log in using their patient identifier and password."""
    serializer = PatientLoginSerializer(data=request.data)
    if serializer.is_valid():
        patient = serializer.validated_data['patient']
        queue_login_notification(
            recipient_email=patient.email,
            user_name=patient.get_full_name(),
            tenant_id=patient.tenant.public_id,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        refresh = RefreshToken()
        refresh['patient_id'] = patient.id
        refresh['tenant_id'] = str(patient.tenant.public_id)
        refresh['login_id'] = patient.login_id
        refresh['is_patient'] = True
        return Response({
            'patient': {
                'id': patient.id,
                'login_id': patient.login_id,
                'hospital_number': patient.hospital_number,
                'mrn': patient.mrn,
                'full_name': patient.get_full_name(),
                'tenant': patient.tenant.name,
            },
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'is_patient': True,
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PatientViewSet(TenantScopedModelViewSet):
    """ViewSet for managing patients."""
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]

    def _can_manage_mpi(self):
        user = self.request.user
        role = getattr(getattr(user, 'tenant_user', None), 'role', None) or getattr(user, 'role', None)
        return bool(
            getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
            or role in {'admin', 'tenant_admin', 'super_admin', 'system_admin'}
        )
    
    def _get_patient_from_request(self):
        user = getattr(self.request, 'user', None)
        if not getattr(user, 'is_authenticated', False):
            return None

        if isinstance(user, Patient):
            return user

        if getattr(user, 'is_patient', False) or getattr(user, 'role', None) == 'patient':
            patient_id = getattr(user, 'patient_id', None) or getattr(user, 'id', None)
            if patient_id is None:
                return None
            try:
                return Patient.objects.get(pk=patient_id)
            except Patient.DoesNotExist:
                return None

        return None

    def get_queryset(self):
        queryset = super().get_queryset().select_related('tenant')
        
        search = self.request.query_params.get('search')
        if search:
            search = search.strip()
            filters = (
                Q(hospital_number__icontains=search) |
                Q(mrn__icontains=search) |
                Q(login_id__icontains=search) |
                Q(nhis_number__icontains=search) |
                Q(nin__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(phone2__icontains=search) |
                Q(email__icontains=search)
            )

            # Full-name search, e.g. "John Smith" (in either order)
            parts = search.split()
            if len(parts) >= 2:
                filters |= (Q(first_name__icontains=parts[0]) & Q(last_name__icontains=parts[-1]))
                filters |= (Q(first_name__icontains=parts[-1]) & Q(last_name__icontains=parts[0]))

            # Numeric primary key search (patient id)
            if search.isdigit():
                filters |= Q(id=int(search))

            queryset = queryset.filter(filters)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter.lower() == 'all':
                pass
            elif status_filter.lower() in ('inactive', 'archived'):
                queryset = queryset.filter(patient_status__in=['inactive', 'archived'])
            else:
                queryset = queryset.filter(patient_status=status_filter)
        else:
            queryset = queryset.filter(is_active=True)
        
        gender_filter = self.request.query_params.get('gender')
        if gender_filter:
            queryset = queryset.filter(gender=gender_filter)
        
        state_filter = self.request.query_params.get('state')
        if state_filter:
            queryset = queryset.filter(state__iexact=state_filter)
        
        return queryset

    # ===== Duplicate detection =====
    def _find_duplicate(self, first_name, last_name, date_of_birth, exclude_id=None):
        """Return an existing patient that matches the same name + date of birth
        within the current tenant (case-insensitive), or None.

        Used to prevent creating duplicate patient records.
        """
        from django.utils.dateparse import parse_date

        if not (first_name and last_name and date_of_birth):
            return None

        if isinstance(date_of_birth, str):
            dob = parse_date(date_of_birth)
            if dob is None:
                try:
                    from datetime import datetime
                    dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
        else:
            dob = date_of_birth

        tenant = self.get_tenant()
        if tenant is None:
            return None

        qs = Patient.objects.filter(
            tenant=tenant,
            first_name__iexact=str(first_name).strip(),
            last_name__iexact=str(last_name).strip(),
            date_of_birth=dob,
        )
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        return qs.first()

    def retrieve(self, request, *args, **kwargs):
        """Log every patient file view as an immutable audit entry."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        self._write_audit_log(
            'view_patient',
            getattr(instance, 'id', None),
            new_values=self._serialize_for_audit(instance),
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='journey')
    def journey(self, request, pk=None):
        """Return the tenant-scoped clinical and billing journey for a patient."""
        user = request.user
        role = getattr(getattr(user, 'tenant_user', None), 'role', None) or getattr(user, 'role', None)
        allowed_roles = {'admin', 'tenant_admin', 'doctor', 'receptionist', 'nurse', 'pharmacist', 'accountant', 'billing_officer', 'super_admin', 'system_admin'}
        if role not in allowed_roles and not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({'detail': 'You do not have permission to view this patient journey.'}, status=status.HTTP_403_FORBIDDEN)

        patient = self.get_object()
        from clinical.serializers import ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer
        from billing.serializers import InvoiceSerializer
        from pharmacy.serializers import DispenseSerializer

        visits = PatientVisit.objects.filter(patient=patient, tenant=patient.tenant).order_by('-checkin_time', '-id')
        prescriptions = patient.prescriptions.select_related('prescribed_by', 'dispensed_by', 'visit').order_by('-prescribed_date')
        vitals = patient.vital_signs.select_related('recorded_by', 'visit').order_by('-recorded_at')
        consultations = patient.consultation_notes.select_related('doctor', 'visit').order_by('-created_at')
        dispenses = patient.dispenses.select_related('drug', 'dispensed_by', 'prescription', 'prescription__prescribed_by').order_by('-dispensed_date')
        invoices = patient.invoices.prefetch_related('items', 'payments').order_by('-invoice_date')

        return Response({
            'patient': self.get_serializer(patient).data,
            'visits': PatientVisitSerializer(visits, many=True).data,
            'consultations': ConsultationNoteSerializer(consultations, many=True).data,
            'prescriptions': PrescriptionSerializer(prescriptions, many=True).data,
            'vitals': VitalSignSerializer(vitals, many=True).data,
            'dispenses': DispenseSerializer(dispenses, many=True).data,
            'invoices': InvoiceSerializer(invoices, many=True).data,
        })

    def create(self, request, *args, **kwargs):
        """Create a patient, blocking duplicate name + DOB records.

        When a potential duplicate is detected the API responds with HTTP 409
        and the existing patient's data so the client can warn the user and
        offer an explicit override via ``confirm_duplicate``.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.data.get('confirm_duplicate'):
            duplicate = self._find_duplicate(
                serializer.validated_data.get('first_name'),
                serializer.validated_data.get('last_name'),
                serializer.validated_data.get('date_of_birth'),
            )
            if duplicate is not None:
                existing = PatientSerializer(
                    duplicate, context=self.get_serializer_context()
                ).data
                return Response(
                    {
                        'duplicate': True,
                        'detail': (
                            'A patient with the same name and date of birth already '
                            'exists. Please verify before creating a duplicate record.'
                        ),
                        'existing_patient': existing,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(detail=False, methods=['post'])
    def check_duplicate(self, request):
        """Lightweight duplicate lookup used by the registration form to warn
        the user before they submit."""
        data = request.data
        duplicate = self._find_duplicate(
            data.get('first_name'),
            data.get('last_name'),
            data.get('date_of_birth'),
        )
        if duplicate is None:
            return Response({'duplicate': False})

        existing = PatientSerializer(
            duplicate, context=self.get_serializer_context()
        ).data
        return Response({'duplicate': True, 'existing_patient': existing})

    @action(detail=True, methods=['post'])
    def merge(self, request, pk=None):
        """Merge this duplicate into the selected canonical survivor record."""
        if not self._can_manage_mpi():
            return Response({'detail': 'Only administrators can merge patient records.'}, status=status.HTTP_403_FORBIDDEN)
        source = self.get_object()
        survivor_id = request.data.get('survivor_id')
        if not survivor_id:
            return Response({'survivor_id': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            merge_record = merge_patients(source.pk, int(survivor_id), self.get_tenant(), request.user, request.data.get('reason', ''))
        except (Patient.DoesNotExist, ValueError):
            return Response({'detail': 'Both patient records must belong to this tenant.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            if hasattr(exc, 'detail'):
                return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
            raise
        self._write_audit_log('merge_patient', source.pk, new_values={
            'survivor_patient_id': merge_record.survivor_patient_id,
            'merge_record_id': merge_record.pk,
            'reason': merge_record.reason,
        })
        return Response(PatientMergeSerializer(merge_record, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='unmerge')
    def unmerge(self, request, pk=None):
        """Reverse the active merge originating from this patient."""
        if not self._can_manage_mpi():
            return Response({'detail': 'Only administrators can unmerge patient records.'}, status=status.HTTP_403_FORBIDDEN)
        source = self.get_object()
        merge_record = PatientMerge.objects.filter(
            source_patient=source, tenant=self.get_tenant(), status='active'
        ).first()
        if merge_record is None:
            return Response({'detail': 'No active merge exists for this patient.'}, status=status.HTTP_404_NOT_FOUND)
        merge_record = unmerge_patient(merge_record, request.user)
        self._write_audit_log('unmerge_patient', source.pk, new_values={'merge_record_id': merge_record.pk})
        return Response(PatientMergeSerializer(merge_record, context=self.get_serializer_context()).data)

    @action(detail=False, methods=['get'])
    def mpi(self, request):
        """Search the Master Patient Index, including inactive merged charts."""
        if not self._can_manage_mpi():
            return Response({'detail': 'Only administrators can access the Master Patient Index.'}, status=status.HTTP_403_FORBIDDEN)
        query = request.query_params.get('search', '').strip()
        queryset = Patient.objects.filter(tenant=self.get_tenant()).select_related('merged_into')
        if query:
            queryset = queryset.filter(
                Q(hospital_number__icontains=query) | Q(mrn__icontains=query) |
                Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                Q(middle_name__icontains=query) | Q(phone__icontains=query) |
                Q(nin__icontains=query) | Q(nhis_number__icontains=query) |
                Q(email__icontains=query)
            )
        queryset = queryset.order_by('-is_active', '-registration_date')[:100]
        return Response({
            'results': [
                {
                    **PatientSerializer(patient, context=self.get_serializer_context()).data,
                    'is_merged': bool(patient.merged_into_id),
                    'survivor_id': patient.merged_into_id,
                }
                for patient in queryset
            ],
            'count': queryset.count(),
        })

    @action(detail=False, methods=['get'], url_path='merge-history')
    def merge_history(self, request):
        if not self._can_manage_mpi():
            return Response({'detail': 'Only administrators can access merge history.'}, status=status.HTTP_403_FORBIDDEN)
        records = PatientMerge.objects.filter(tenant=self.get_tenant()).select_related('source_patient', 'survivor_patient', 'merged_by')
        return Response(PatientMergeSerializer(records, many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='refresh-password')
    def refresh_password(self, request, pk=None):
        """Generate and save a fresh login password for a patient.

        Restricted to tenant root admins or global admins. This mirrors the staff
        password refresh rules and prevents lower-privilege users from resetting
        patient credentials.
        """
        user = request.user
        tenant_user = getattr(user, 'tenant_user', None)
        is_root_admin = bool(
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in {'super_admin', 'system_admin'}
            or getattr(tenant_user, 'is_root_admin', False)
        )
        if not is_root_admin:
            return Response(
                {'detail': 'Only the root admin can refresh a patient password.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        patient = self.get_object()
        generated_password = str(request.data.get('password') or '').strip() or self._generate_temp_password()

        patient.set_password(generated_password)
        patient.save(update_fields=['password'])

        return Response({
            'id': patient.id,
            'login_id': patient.login_id or patient.hospital_number or patient.mrn,
            'password': generated_password,
            'message': 'Password refreshed successfully.',
        })

    def _generate_temp_password(self, length=12):
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + '!@#$%'
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    # ===== Audit logging =====
    def _get_client_ip(self):
        request = self.request
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def _resolve_global_user(self):
        """AuditLog.user must be a GlobalUser. Resolve it from the request user,
        which may be a TenantUser (with a global_user link) or a GlobalUser."""
        from users.models import GlobalUser
        user = getattr(self.request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        if isinstance(user, GlobalUser):
            return user
        # TenantUser has an optional OneToOne link to a GlobalUser.
        return getattr(user, 'global_user', None)

    def _write_audit_log(self, action_name, resource_id, old_values=None, new_values=None):
        """Dispatch a tenant-scoped AuditLog write to a background thread.

        This is fully non-blocking: the API request returns without waiting for
        (and is never affected by) the audit insert. Only JSON-safe primitives
        are handed to the worker so no request/ORM objects cross the thread.
        """
        try:
            request = self.request
            tenant = self.get_tenant()
            global_user = self._resolve_global_user()
            user = getattr(request, 'user', None)
            actor = 'system'
            if user is not None and getattr(user, 'is_authenticated', False):
                name = ''
                try:
                    gfn = getattr(user, 'get_full_name', None)
                    if callable(gfn):
                        name = (gfn() or '').strip()
                except Exception:
                    name = ''
                if not name:
                    name = (getattr(user, 'username', None) or getattr(user, 'email', None) or '').strip()
                if name:
                    actor = name
            payload = {
                'tenant_id': getattr(tenant, 'id', None),
                'user_id': getattr(global_user, 'id', None),
                'actor': actor,
                'action': action_name,
                'resource_type': 'patient',
                'resource_id': str(resource_id) if resource_id is not None else '',
                'old_values': old_values,
                'new_values': new_values,
                'ip_address': self._get_client_ip(),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }
            thread = threading.Thread(
                target=_write_audit_log_async,
                args=(payload,),
                daemon=True,
            )
            thread.start()
        except Exception:
            # Dispatching must never interfere with the actual request.
            logger.exception('Failed to dispatch patient audit log for action=%s', action_name)

    def _serialize_for_audit(self, instance):
        """Return a JSON-safe representation of a patient for the audit trail."""
        try:
            return PatientSerializer(instance, context=self.get_serializer_context()).data
        except Exception:
            logger.exception('Failed to serialize patient for audit log')
            return None

    def perform_create(self, serializer):
        super().perform_create(serializer)
        instance = serializer.instance
        self._write_audit_log(
            'create_patient',
            getattr(instance, 'id', None),
            new_values=self._serialize_for_audit(instance),
        )

    def perform_update(self, serializer):
        # Capture the current (pre-save) values before changes are applied.
        old_values = None
        if serializer.instance is not None:
            old_values = self._serialize_for_audit(serializer.instance)

        super().perform_update(serializer)

        instance = serializer.instance
        self._write_audit_log(
            'update_patient',
            getattr(instance, 'id', None),
            old_values=old_values,
            new_values=self._serialize_for_audit(instance),
        )

    def perform_destroy(self, instance):
        resource_id = getattr(instance, 'id', None)
        old_values = self._serialize_for_audit(instance)

        super().perform_destroy(instance)

        self._write_audit_log(
            'delete_patient',
            resource_id,
            old_values=old_values,
        )
    
    @action(detail=True, methods=['get'])
    def audit_history(self, request, pk=None):
        """Return the immutable audit timeline for one patient file."""
        patient = self.get_object()
        queryset = AuditLog.objects.filter(
            resource_type='patient',
            resource_id=str(patient.id),
            tenant=self.get_tenant(),
        ).order_by('-timestamp')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = AuditLogSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = AuditLogSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Return the authenticated patient profile for self-service access."""
        patient = self._get_patient_from_request()
        if patient is None:
            return Response({'detail': 'Patient authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(patient)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def portal(self, request):
        """Provide the authenticated patient with appointments, labs, and documents."""
        patient = self._get_patient_from_request()
        if patient is None:
            return Response({'detail': 'Patient authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        from lab.models import LabOrder
        from lab.serializers import LabOrderSerializer
        from clinical.models import Prescription
        from clinical.serializers import PrescriptionSerializer
        from billing.models import Invoice
        from billing.serializers import InvoiceSerializer

        appointments = patient.appointments.all().order_by('-scheduled_date', '-scheduled_time')
        lab_orders = LabOrder.objects.filter(tenant=patient.tenant, patient=patient).select_related('test').prefetch_related('results').order_by('-ordered_date')
        documents = patient.documents.all().order_by('-upload_date')
        prescriptions = Prescription.objects.filter(
            tenant=patient.tenant, patient=patient
        ).select_related('prescribed_by', 'dispensed_by', 'visit').order_by('-prescribed_date')
        invoices = Invoice.objects.filter(
            tenant=patient.tenant, patient=patient
        ).prefetch_related('items', 'payments', 'insurance_claims').order_by('-invoice_date')
        tenant = patient.tenant
        tenant_logo_url = ''
        if tenant.logo:
            try:
                tenant_logo_url = request.build_absolute_uri(tenant.logo.url)
            except Exception:
                tenant_logo_url = ''

        return Response({
            'patient': PatientSerializer(patient, context=self.get_serializer_context()).data,
            'tenant': {
                'name': tenant.name,
                'code': tenant.code,
                'email': tenant.email,
                'phone': tenant.phone,
                'address': tenant.address,
                'city': tenant.city,
                'state': tenant.state.name if tenant.state else '',
                'facility_type': tenant.facility_type.name if tenant.facility_type else '',
                'website': tenant.website,
                'logo_url': tenant_logo_url,
            },
            'appointments': AppointmentSerializer(appointments, many=True).data,
            'lab_orders': LabOrderSerializer(lab_orders, many=True).data,
            'documents': PatientDocumentSerializer(documents, many=True).data,
            'prescriptions': PrescriptionSerializer(prescriptions, many=True).data,
            'invoices': InvoiceSerializer(invoices, many=True, context=self.get_serializer_context()).data,
            'notifications': [
                {
                    'id': 'welcome',
                    'title': 'Welcome to your portal',
                    'message': f'Hello {patient.get_full_name()}, you can review recent appointments, lab orders, and records here.',
                    'read': True,
                    'createdAt': timezone.now().isoformat(),
                }
            ],
        })

    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search for patients using multiple criteria."""
        serializer = PatientSearchSerializer(data=request.data)
        
        if serializer.is_valid():
            user = request.user
            if not hasattr(user, 'tenant_user') or not user.tenant_user:
                return Response(
                    {'error': 'Must be a tenant user'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            data = serializer.validated_data
            filters = Q()
            if data.get('hospital_number'):
                filters &= Q(hospital_number__icontains=data['hospital_number'])
            if data.get('nhis_number'):
                filters &= Q(nhis_number__icontains=data['nhis_number'])
            if data.get('nin'):
                filters &= Q(nin__icontains=data['nin'])
            if data.get('first_name'):
                filters &= Q(first_name__icontains=data['first_name'])
            if data.get('last_name'):
                filters &= Q(last_name__icontains=data['last_name'])
            if data.get('phone'):
                filters &= Q(phone__icontains=data['phone'])
            if data.get('email'):
                filters &= Q(email__icontains=data['email'])
            
            patients = self.get_queryset().filter(filters)
            page = self.paginate_queryset(patients)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(patients, many=True)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        patient = self.get_object()
        old_values = self._serialize_for_audit(patient)
        patient.patient_status = 'inactive'
        patient.is_active = False
        patient.save(update_fields=['patient_status', 'is_active'])
        self._write_audit_log(
            'delete_patient',
            getattr(patient, 'id', None),
            old_values=old_values,
            new_values=self._serialize_for_audit(patient),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def visits(self, request, pk=None):
        """Get patient's visit history."""
        patient = self.get_object()
        visits = patient.visits.all().order_by('-checkin_time')
        
        page = self.paginate_queryset(visits)
        if page is not None:
            serializer = PatientVisitSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PatientVisitSerializer(visits, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Get patient's documents."""
        patient = self.get_object()
        documents = patient.documents.all().order_by('-upload_date')
        
        page = self.paginate_queryset(documents)
        if page is not None:
            serializer = PatientDocumentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PatientDocumentSerializer(documents, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def allergies(self, request, pk=None):
        """Get patient's allergies."""
        patient = self.get_object()
        allergies = patient.allergies.all().order_by('-severity')
        
        page = self.paginate_queryset(allergies)
        if page is not None:
            serializer = PatientAllergySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PatientAllergySerializer(allergies, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def medications(self, request, pk=None):
        """Get patient's current medications."""
        patient = self.get_object()
        medications = patient.current_medications.filter(status='active')
        
        page = self.paginate_queryset(medications)
        if page is not None:
            serializer = PatientMedicationSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PatientMedicationSerializer(medications, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def appointments(self, request, pk=None):
        """Get patient's appointments."""
        patient = self.get_object()
        appointments = patient.appointments.all().order_by('-scheduled_date', '-scheduled_time')
        
        page = self.paginate_queryset(appointments)
        if page is not None:
            serializer = AppointmentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = AppointmentSerializer(appointments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """Check in patient for a visit."""
        patient = self.get_object()
        user = request.user
        
        if not hasattr(user, 'tenant_user') or not user.tenant_user:
            return Response(
                {'error': 'Must be a tenant user'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create a new visit
        visit = PatientVisit.objects.create(
            tenant=user.tenant_user.tenant,
            patient=patient,
            visit_type=request.data.get('visit_type', 'opd'),
            chief_complaint=request.data.get('chief_complaint', ''),
            triage_category=request.data.get('triage_category', 'green')
        )
        
        # Update patient's last visit
        patient.last_visit = timezone.now()
        patient.save()
        
        serializer = PatientVisitSerializer(visit)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PatientVisitViewSet(TenantScopedModelViewSet):
    """ViewSet for managing patient visits."""
    queryset = PatientVisit.objects.all()
    serializer_class = PatientVisitSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'patient', 'doctor', 'nurse', 'department'
        )
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(visit_status=status_filter)
        
        date_filter = self.request.query_params.get('date')
        if date_filter:
            queryset = queryset.filter(checkin_time__date=date_filter)
        
        doctor_filter = self.request.query_params.get('doctor_id')
        if doctor_filter:
            queryset = queryset.filter(doctor_id=doctor_filter)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def triage(self, request, pk=None):
        """Update triage information."""
        visit = self.get_object()
        
        # Check permissions
        user = request.user
        if not hasattr(user, 'tenant_user') or user.tenant_user.role not in ['nurse', 'doctor']:
            raise permissions.PermissionDenied("Only medical staff can triage patients")
        
        # Update triage
        visit.vital_signs = request.data.get('vital_signs', {})
        visit.triage_category = request.data.get('triage_category', visit.triage_category)
        visit.triage_time = timezone.now()
        visit.visit_status = 'triaged'
        visit.nurse = user.tenant_user
        visit.save()
        
        serializer = self.get_serializer(visit)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def start_consultation(self, request, pk=None):
        """Start consultation."""
        visit = self.get_object()
        
        # Check permissions
        user = request.user
        if not hasattr(user, 'tenant_user') or user.tenant_user.role != 'doctor':
            raise permissions.PermissionDenied("Only doctors can start consultations")
        
        # Start consultation
        visit.doctor = user.tenant_user
        visit.consultation_start_time = timezone.now()
        visit.visit_status = 'in_consultation'
        visit.save()
        
        serializer = self.get_serializer(visit)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def end_consultation(self, request, pk=None):
        """End consultation and persist full clinical documentation."""
        visit = self.get_object()
        
        user = request.user
        if not hasattr(user, 'tenant_user') or user.tenant_user.role != 'doctor':
            raise permissions.PermissionDenied("Only doctors can end consultations")
        
        # Update visit with consultation data and disposition
        visit.chief_complaint = request.data.get('chief_complaint', visit.chief_complaint)
        visit.history_of_present_illness = request.data.get('history_of_present_illness', visit.history_of_present_illness)
        visit.referral_from = request.data.get('referral_from', visit.referral_from)
        visit.referral_reason = request.data.get('referral_reason', visit.referral_reason)
        visit.consultation_end_time = timezone.now()
        visit.visit_status = request.data.get('next_status', 'awaiting_lab')
        
        # Disposition & Follow-up
        visit.disposition_type = request.data.get('disposition_type', visit.disposition_type)
        visit.disposition_reason = request.data.get('disposition_reason', visit.disposition_reason)
        visit.admission_required = request.data.get('admission_required', visit.admission_required)
        visit.follow_up_date = request.data.get('follow_up_date', visit.follow_up_date)
        visit.follow_up_time = request.data.get('follow_up_time', visit.follow_up_time)
        visit.follow_up_reason = request.data.get('follow_up_reason', visit.follow_up_reason)
        
        visit.save()
        
        # Create or update comprehensive consultation note
        from clinical.models import ConsultationNote, Prescription
        
        latest_note = ConsultationNote.objects.filter(visit=visit).order_by('-created_at').first()
        if latest_note:
            ConsultationNote.objects.filter(visit=visit).exclude(pk=latest_note.pk).delete()
        
        consultation_note, created = ConsultationNote.objects.update_or_create(
            visit=visit,
            defaults={
                'tenant': visit.tenant,
                'patient': visit.patient,
                'doctor': user.tenant_user,
                'chief_complaint': request.data.get('chief_complaint', ''),
                'history_of_present_illness': request.data.get('history_of_present_illness', ''),
                'duration': request.data.get('duration', ''),
                'timing': request.data.get('timing', ''),
                'hpi_details': request.data.get('hpi_details', {}),
                'is_signed': request.data.get('is_signed', False),
                'signed_at': request.data.get('signed_at'),
                'subjective': request.data.get('subjective', ''),
                'objective': request.data.get('objective', ''),
                'assessment': request.data.get('assessment', ''),
                'plan': request.data.get('plan', ''),
                'diagnosis_codes': request.data.get('diagnosis_codes', []),
                'differential_diagnosis': request.data.get('differential_diagnosis', ''),
                'ice_ideas': request.data.get('ice_ideas', ''),
                'ice_concerns': request.data.get('ice_concerns', ''),
                'ice_expectations': request.data.get('ice_expectations', ''),
                'allergies': request.data.get('allergies', []),
                'past_medical_history': request.data.get('past_medical_history', {}),
                'family_history': request.data.get('family_history', {}),
                'social_history': request.data.get('social_history', {}),
                'physical_exam': request.data.get('physical_exam', {}),
                'disposition_type': request.data.get('disposition_type', ''),
                'disposition_reason': request.data.get('disposition_reason', ''),
                'admission_required': request.data.get('admission_required', False),
                'follow_up_date': request.data.get('follow_up_date'),
                'follow_up_time': request.data.get('follow_up_time'),
                'follow_up_reason': request.data.get('follow_up_reason', ''),
                'billing_items': request.data.get('billing_items', []),
                'insurance_covered': request.data.get('insurance_covered', False),
                'insurance_amount': request.data.get('insurance_amount', 0),
                'is_final': request.data.get('is_final', True)
            }
        )
        
        # Replace the visit's prescriptions with the signed consultation list.
        prescriptions = request.data.get('prescriptions', [])
        Prescription.objects.filter(visit=visit).delete()
        for prescription_data in prescriptions:
            Prescription.objects.create(
                tenant=visit.tenant,
                visit=visit,
                patient=visit.patient,
                prescribed_by=user.tenant_user,
                drug_name=prescription_data.get('drug_name', prescription_data.get('medication', '')),
                dosage=prescription_data.get('dosage', prescription_data.get('dose', '')),
                frequency=prescription_data.get('frequency', ''),
                duration=str(prescription_data.get('duration', '') or ''),
                quantity=int(prescription_data.get('quantity', 1) or 1),
                route=str(prescription_data.get('route', 'oral') or 'oral').lower(),
                instructions=prescription_data.get('instructions', ''),
                special_instructions=prescription_data.get('special_instructions', ''),
                status='prescribed'
            )
        
        # Create lab orders (auto-approved)
        lab_orders = request.data.get('lab_orders', [])
        if lab_orders:
            from lab.models import LabOrder, LabTest
            for order_index, order_data in enumerate(lab_orders, start=1):
                test = None
                test_id = order_data.get('test_id')
                test_name = order_data.get('test_name') or order_data.get('test') or ''
                if test_id:
                    test = LabTest.objects.filter(id=test_id, tenant=visit.tenant).first()
                if not test and test_name:
                    test = LabTest.objects.filter(tenant=visit.tenant).filter(
                        Q(name__iexact=test_name) | Q(code__iexact=test_name)
                    ).first()
                if not test:
                    code = slugify(test_name or f'lab_test_{order_index}')[:45] or f'LAB-{visit.id}-{order_index}'
                    if LabTest.objects.filter(tenant=visit.tenant, code=code).exists():
                        test = LabTest.objects.filter(tenant=visit.tenant, code=code).first()
                    else:
                        test = LabTest.objects.create(
                            tenant=visit.tenant,
                            name=test_name or f'Lab order {order_index}',
                            code=code,
                            category='other',
                            sample_type='Blood',
                            turnaround_time=24,
                            price=0
                        )
                
                LabOrder.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    visit=visit,
                    order_number=f"LO-{timezone.now().strftime('%Y%m%d%H%M%S%f')}-{visit.id}-{order_index}",
                    test=test,
                    clinical_notes=order_data.get('clinical_notes', ''),
                    status='in_progress',
                    priority=order_data.get('priority', 'routine'),
                    ordered_by=user.tenant_user
                )
        
        # Persist radiology, procedure, and referral requests as patient documents
        radiology_orders = request.data.get('radiology_orders', [])
        procedure_orders = request.data.get('procedure_orders', [])
        referral_orders = request.data.get('referral_orders', [])
        if radiology_orders or procedure_orders or referral_orders:
            for index, order_data in enumerate(radiology_orders, start=1):
                PatientDocument.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    document_type='radiology',
                    title=order_data.get('study', f'Radiology order {index}'),
                    description=(f"Priority: {order_data.get('priority', 'routine')}\nStatus: Approved\n" + order_data.get('notes', '')).strip(),
                    uploaded_by=user.tenant_user,
                    document_date=timezone.now().date()
                )
            for index, order_data in enumerate(procedure_orders, start=1):
                PatientDocument.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    document_type='other',
                    title=f"Procedure: {order_data.get('procedure', 'Procedure order')}",
                    description=(f"Priority: {order_data.get('priority', 'routine')}\nStatus: Approved\n" + order_data.get('notes', '')).strip(),
                    uploaded_by=user.tenant_user,
                    document_date=timezone.now().date()
                )
            for index, order_data in enumerate(referral_orders, start=1):
                PatientDocument.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    document_type='referral',
                    title=order_data.get('referral', f'Referral order {index}'),
                    description=(f"Priority: {order_data.get('priority', 'routine')}\nStatus: Approved\n" + order_data.get('notes', '')).strip(),
                    uploaded_by=user.tenant_user,
                    document_date=timezone.now().date()
                )
        
        # Create billing invoice if billing items exist
        billing_items = request.data.get('billing_items', [])
        if billing_items:
            from billing.models import Invoice
            invoice_number = f"INV-{timezone.now().strftime('%Y%m%d%H%M%S')}-{visit.id}"
            subtotal = sum([float(item.get('amount', 0) or 0) for item in billing_items])
            invoice = Invoice.objects.create(
                tenant=visit.tenant,
                patient=visit.patient,
                visit=visit,
                invoice_number=invoice_number,
                due_date=timezone.now() + timezone.timedelta(days=30),
                subtotal=subtotal,
                tax_amount=0,
                discount_amount=0,
                total_amount=subtotal,
                amount_paid=0,
                balance_due=subtotal,
                status='issued',
                insurance_covered=request.data.get('insurance_covered', False),
                insurance_amount=request.data.get('insurance_amount', 0),
                patient_amount=subtotal - float(request.data.get('insurance_amount', 0) or 0)
            )
        
        serializer = self.get_serializer(visit)
        return Response(serializer.data)


class AppointmentViewSet(TenantScopedModelViewSet):
    """ViewSet for managing appointments."""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        request_data = request.data.copy()
        request_user = request.user
        is_patient = bool(getattr(request_user, 'is_patient', False))

        if is_patient:
            patient_id = getattr(request_user, 'patient_id', None) or getattr(request_user, 'id', None)
            if not patient_id:
                return Response({'detail': 'Patient identity could not be determined.'}, status=status.HTTP_401_UNAUTHORIZED)
            request_data['patient'] = patient_id

        # Portal forms may submit human-readable doctor or department names.
        # Staff forms continue to submit primary-key values.
        tenant = self.get_tenant()
        doctor_value = request_data.get('doctor')
        if doctor_value and not str(doctor_value).isdigit():
            doctor = TenantUser.objects.filter(
                tenant=tenant,
                role='doctor',
                is_active=True,
            ).filter(
                Q(email__iexact=str(doctor_value)) |
                Q(employee_id__iexact=str(doctor_value)) |
                Q(username__iexact=str(doctor_value))
            ).first()
            if doctor is None:
                doctor_parts = str(doctor_value).split()
                if len(doctor_parts) >= 2:
                    doctor = TenantUser.objects.filter(
                        tenant=tenant,
                        role='doctor',
                        is_active=True,
                        first_name__iexact=doctor_parts[0],
                        last_name__iexact=' '.join(doctor_parts[1:]),
                    ).first()
            if doctor:
                request_data['doctor'] = doctor.id
            else:
                request_data['doctor'] = None

        department_value = request_data.get('department')
        if department_value and not str(department_value).isdigit():
            department = Department.objects.filter(
                tenant=tenant,
                name__iexact=str(department_value),
            ).first()
            request_data['department'] = department.id if department else None

        serializer = self.get_serializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        # Use perform_create so TenantScopedModelViewSet injects the tenant
        self.perform_create(serializer)
        appointment = serializer.instance

        reminder_result = {'status': 'skipped', 'channels': []}
        send_reminder = request.data.get('send_reminder', True)
        if send_reminder:
            reminder_result = _dispatch_appointment_reminder(
                appointment,
                channels=request.data.get('reminder_channels') or [],
                preferred_channel=request.data.get('preferred_channel'),
            )
        elif appointment.doctor and appointment.doctor.email:
            self._notify_assigned_doctor(appointment)

        headers = self.get_success_headers(serializer.data)
        response_data = dict(serializer.data)
        if send_reminder and reminder_result.get('error'):
            response_data['notification_warning'] = reminder_result['error']
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

    def _notify_assigned_doctor(self, appointment):
        doctor = appointment.doctor
        if not doctor or not doctor.email:
            return
        try:
            dispatch_email_task(send_appointment_email_task, args=(appointment.id, 'doctor'))
        except Exception:
            logger.exception('Failed to notify doctor %s for appointment %s', doctor.id, appointment.id)

    def update(self, request, *args, **kwargs):
        appointment = self.get_object()
        previous_doctor_id = appointment.doctor_id
        response = super().update(request, *args, **kwargs)
        updated_appointment = self.get_object()
        if not previous_doctor_id and updated_appointment.doctor_id:
            self._notify_assigned_doctor(updated_appointment)
        return response
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'patient', 'doctor', 'department', 'created_by', 'updated_by'
        )
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date and end_date:
            queryset = queryset.filter(
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date
            )
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        doctor_filter = self.request.query_params.get('doctor_id')
        if doctor_filter:
            queryset = queryset.filter(doctor_id=doctor_filter)
        else:
            if getattr(self.request.user, 'is_patient', False):
                patient_id = getattr(self.request.user, 'patient_id', None) or getattr(self.request.user, 'id', None)
                queryset = queryset.filter(patient_id=patient_id)
            else:
                tenant_user = getattr(self.request.user, 'tenant_user', None)
                if tenant_user and getattr(tenant_user, 'role', None) == 'doctor':
                    queryset = queryset.filter(doctor_id=tenant_user.id)
        
        return queryset.order_by('scheduled_date', 'scheduled_time')
    
    @action(detail=False, methods=['post'])
    def schedule(self, request):
        """Schedule a new appointment."""
        serializer = AppointmentScheduleSerializer(data=request.data)
        
        if serializer.is_valid():
            user = request.user
            if not hasattr(user, 'tenant_user') or not user.tenant_user:
                return Response(
                    {'error': 'Must be a tenant user'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            data = serializer.validated_data
            tenant = user.tenant_user.tenant
            
            # Get patient
            patient = get_object_or_404(Patient, id=data['patient_id'], tenant=tenant)
            
            # Get doctor
            doctor = get_object_or_404(
                TenantUser,
                id=data['doctor_id'],
                tenant=tenant,
                role='doctor'
            )
            
            # Create appointment
            appointment = Appointment.objects.create(
                tenant=tenant,
                patient=patient,
                doctor=doctor,
                department=data.get('department_id'),
                appointment_type=data['appointment_type'],
                scheduled_date=data['scheduled_date'],
                scheduled_time=data['scheduled_time'],
                reason=data.get('reason', ''),
                notes=data.get('notes', '')
            )

            if data.get('send_reminder', False):
                reminder_channels = data.get('reminder_channels') or []
                preferred_channel = data.get('preferred_channel')
                _dispatch_appointment_reminder(
                    appointment,
                    channels=reminder_channels,
                    preferred_channel=preferred_channel,
                )
            
            serializer = AppointmentSerializer(appointment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm an appointment."""
        appointment = self.get_object()
        appointment.status = 'confirmed'
        appointment.save()

        if request.data.get('send_reminder', False):
            _dispatch_appointment_reminder(
                appointment,
                channels=request.data.get('reminder_channels') or [],
                preferred_channel=request.data.get('preferred_channel'),
            )
        
        serializer = self.get_serializer(appointment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an appointment."""
        appointment = self.get_object()
        appointment.status = 'cancelled'
        appointment.save()
        
        # TODO: Send cancellation notification
        
        serializer = self.get_serializer(appointment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_reminder(self, request, pk=None):
        """Send a reminder message for an appointment."""
        appointment = self.get_object()
        reminder_result = _dispatch_appointment_reminder(
            appointment,
            channels=request.data.get('reminder_channels') or [],
            preferred_channel=request.data.get('preferred_channel'),
        )
        return Response({
            'appointment': AppointmentSerializer(appointment).data,
            'reminder': reminder_result,
        })

    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """Check in for appointment."""
        appointment = self.get_object()
        
        # Create a visit from appointment
        visit = PatientVisit.objects.create(
            tenant=appointment.tenant,
            patient=appointment.patient,
            visit_type='opd',
            chief_complaint=appointment.reason or 'Appointment follow-up',
            doctor=appointment.doctor,
            department=appointment.department,
            visit_status='checked_in',
            checkin_time=timezone.now()
        )
        
        # Update appointment status
        appointment.status = 'checked_in'
        appointment.save()
        
        return Response({
            'appointment': AppointmentSerializer(appointment).data,
            'visit': PatientVisitSerializer(visit).data
        })


class BulkPatientUploadViewSet(TenantScopedModelViewSet):
    """ViewSet for tracking bulk patient uploads."""
    queryset = BulkPatientUpload.objects.all()
    serializer_class = BulkPatientUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'], serializer_class=BulkPatientUploadSerializer)
    def upload(self, request):
        """Accept file upload and start background processing."""
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        tenant = self.get_tenant()
        if not tenant:
            return Response({'error': 'No tenant associated with your account.'}, status=status.HTTP_400_BAD_REQUEST)

        upload = BulkPatientUpload.objects.create(
            tenant=tenant,
            uploaded_by=request.user.tenant_user if hasattr(request.user, 'tenant_user') else None,
            file=file_obj,
            original_filename=file_obj.name,
            status='processing',
            started_at=timezone.now(),
        )

        thread = threading.Thread(target=_process_bulk_upload, args=(upload.id,))
        thread.start()

        serializer = self.get_serializer(upload)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _bool_val(value):
    """Convert CSV truthy/falsy strings ('TRUE', 'FALSE', '1', '0', 'yes'...) to a Python bool."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    sval = str(value).strip().lower()
    return sval in ('true', '1', 'yes', 'y', 't')


def _parse_date_val(value):
    """Parse a date string in common formats; return None for empty input."""
    if not value or not str(value).strip():
        return None
    from datetime import datetime
    dof = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(dof, fmt).date()
        except Exception:
            pass
    raise ValueError(f'Invalid date format: {dof}')


def _process_bulk_upload(upload_id):
    """Background processor for bulk patient uploads."""
    from django.db import transaction, close_old_connections
    close_old_connections()
    try:
        upload = BulkPatientUpload.objects.get(id=upload_id)
        upload.status = 'processing'
        upload.started_at = timezone.now()
        upload.save(update_fields=['status', 'started_at'])

        file_path = upload.file.path
        errors = []
        success_count = 0
        failure_count = 0
        total_records = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total_records = len(rows)
                upload.total_records = total_records
                upload.save(update_fields=['total_records'])

                for idx, row in enumerate(rows):
                    try:
                        dof = row.get('date_of_birth') or row.get('Date of Birth') or ''
                        dob = None
                        if dof:
                            try:
                                from datetime import datetime
                                dob = datetime.strptime(dof.strip(), '%Y-%m-%d').date()
                            except Exception:
                                try:
                                    dob = datetime.strptime(dof.strip(), '%d/%m/%Y').date()
                                except Exception:
                                    try:
                                        dob = datetime.strptime(dof.strip(), '%m/%d/%Y').date()
                                    except Exception:
                                        raise ValueError(f'Invalid date format for date_of_birth: {dof}')

                        validated_data = {
                            'first_name': (row.get('first_name') or row.get('First Name') or '').strip(),
                            'last_name': (row.get('last_name') or row.get('Last Name') or '').strip(),
                            'middle_name': (row.get('middle_name') or row.get('Middle Name') or '').strip(),
                            'date_of_birth': dob,
                            'gender': (row.get('gender') or row.get('Gender') or 'unknown').lower(),
                            'marital_status': (row.get('marital_status') or row.get('Marital Status') or 'single').lower(),
                            'phone': (row.get('phone') or row.get('Phone') or '').strip(),
                            'phone2': (row.get('phone2') or row.get('Phone 2') or '').strip(),
                            'email': (row.get('email') or row.get('Email') or '').strip(),
                            'address': (row.get('address') or row.get('Address') or '').strip(),
                            'city': (row.get('city') or row.get('City') or '').strip(),
                            'state': (row.get('state') or row.get('State') or 'Rivers').strip(),
                            'lga': (row.get('lga') or row.get('LGA') or '').strip(),
                            'country': (row.get('country') or row.get('Country') or 'Nigeria').strip(),
                            'blood_group': (row.get('blood_group') or row.get('Blood Group') or 'unknown').strip(),
                            'genotype': (row.get('genotype') or row.get('Genotype') or 'unknown').strip(),
                            'next_of_kin_name': (row.get('next_of_kin_name') or row.get('Next of Kin Name') or '').strip(),
                            'next_of_kin_relationship': (row.get('next_of_kin_relationship') or row.get('Next of Kin Relationship') or '').strip(),
                            'next_of_kin_phone': (row.get('next_of_kin_phone') or row.get('Next of Kin Phone') or '').strip(),
                            'next_of_kin_address': (row.get('next_of_kin_address') or row.get('Next of Kin Address') or '').strip(),
                            'known_allergies': (row.get('known_allergies') or row.get('Known Allergies') or '').strip(),
                            'chronic_conditions': (row.get('chronic_conditions') or row.get('Chronic Conditions') or '').strip(),
                            'current_medications': (row.get('current_medications') or row.get('Current Medications') or '').strip(),
                            'surgical_history': (row.get('surgical_history') or row.get('Surgical History') or '').strip(),
                            'family_history': (row.get('family_history') or row.get('Family History') or '').strip(),
                            'has_insurance': _bool_val(row.get('has_insurance')),
                            'insurance_company': (row.get('insurance_company') or row.get('Insurance Company') or '').strip(),
                            'insurance_policy_number': (row.get('insurance_policy_number') or row.get('Insurance Policy Number') or '').strip(),
                            'insurance_expiry': _parse_date_val(row.get('insurance_expiry')),
                            'occupation': (row.get('occupation') or row.get('Occupation') or '').strip(),
                            'religion': (row.get('religion') or row.get('Religion') or '').strip(),
                            'ethnicity': (row.get('ethnicity') or row.get('Ethnicity') or '').strip(),
                            'language_spoken': (row.get('language_spoken') or row.get('Language Spoken') or 'English').strip(),
                            'preferred_language': (row.get('preferred_language') or row.get('Preferred Language') or '').strip() or 'English',
                            'patient_status': (row.get('patient_status') or row.get('Patient Status') or 'active').lower(),
                            'notes': (row.get('notes') or row.get('Notes') or '').strip(),
                            'nhis_number': (row.get('nhis_number') or row.get('NHIS Number') or '').strip(),
                            'nin': (row.get('nin') or row.get('NIN') or '').strip(),
                            'dnr_order': _bool_val(row.get('dnr_order')),
                            'dnr_order_reason': (row.get('dnr_order_reason') or row.get('DNR Order Reason') or '').strip(),
                            'dnr_order_date': _parse_date_val(row.get('dnr_order_date')),
                            'login_id': (row.get('login_id') or row.get('Login ID') or '').strip(),
                            'password': (row.get('password') or row.get('Password') or '').strip() or None,
                        }

                        if not validated_data['first_name'] or not validated_data['last_name']:
                            raise ValueError('First name and last name are required.')

                        if not validated_data['phone']:
                            raise ValueError('Phone number is required.')

                        if not validated_data['date_of_birth']:
                            raise ValueError('Date of birth is required.')

                        existing = Patient.objects.filter(
                            tenant=upload.tenant,
                            first_name__iexact=validated_data['first_name'],
                            last_name__iexact=validated_data['last_name'],
                            date_of_birth=validated_data['date_of_birth'],
                        ).first()
                        if existing is not None:
                            raise ValueError(
                                'Duplicate patient: a record with the same name and '
                                f'date of birth already exists (Hospital No: {existing.hospital_number}).'
                            )

                        with transaction.atomic(using='default'):
                            _password = validated_data.pop('password', None)
                            patient = Patient(tenant=upload.tenant, **validated_data)
                            patient.save()
                            if _password:
                                patient.set_password(_password)
                                patient.save(update_fields=['password'])
                        success_count += 1
                    except Exception as row_err:
                        failure_count += 1
                        errors.append({
                            'row': idx + 2,
                            'data': dict(row),
                            'error': f"{type(row_err).__name__}: {str(row_err)}"
                        })

                    upload.processed_records = idx + 1
                    upload.success_count = success_count
                    upload.failure_count = failure_count
                    upload.errors = errors
                    try:
                        upload.save(update_fields=['processed_records', 'success_count', 'failure_count', 'errors'])
                    except Exception:
                        pass

            upload.status = 'completed'
            upload.completed_at = timezone.now()
            upload.result_message = f"Processed {total_records} records. {success_count} succeeded, {failure_count} failed."
            upload.save(update_fields=['status', 'completed_at', 'result_message'])

        except Exception as e:
            import traceback
            upload.status = 'failed'
            upload.completed_at = timezone.now()
            upload.result_message = str(e)
            upload.save(update_fields=['status', 'completed_at', 'result_message'])

    except BulkPatientUpload.DoesNotExist:
        pass


# ==================== PATIENT PASSWORD RESET VIEWS ====================


class PatientPasswordResetRequestView(APIView):
    """Request a password reset token for a patient."""
    permission_classes = [permissions.AllowAny]
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def post(self, request):
        serializer = PatientPasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        identifier = serializer.validated_data['identifier'].strip()
        ip_address = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        patient = None
        
        if identifier:
            # Try to find patient by hospital_number, login_id, mrn, or email
            patient = Patient.objects.filter(hospital_number__iexact=identifier).first()
            if not patient:
                patient = Patient.objects.filter(login_id__iexact=identifier).first()
            if not patient:
                patient = Patient.objects.filter(mrn__iexact=identifier).first()
            if not patient:
                patient = Patient.objects.filter(email__iexact=identifier).first()
        
        if patient and patient.email:
            recipient_email = patient.email
            reset_token = PasswordResetToken.objects.create(
                email=recipient_email,
                token=f'{secrets.randbelow(10**12):012d}',
                expires_at=timezone.now() + timezone.timedelta(hours=1),
                user_type='patient',
                user_id=patient.id,
                ip_address=ip_address,
                user_agent=user_agent
            )

            logger.info('Sending password reset email to patient %s (%s)', patient.id, recipient_email)
            try:
                from smartcare_hms.email_delivery import dispatch_email_task
                dispatch_email_task(
                    send_password_reset_email_task,
                    kwargs={
                        'recipient_email': recipient_email,
                        'reset_token': reset_token.token,
                        'user_name': patient.get_full_name(),
                    },
                )
                logger.info('Password reset email sent to patient %s', patient.id)
            except Exception:
                logger.exception('Unable to send password reset email to patient %s', patient.id)
        
        return Response({
            'detail': 'If an account exists for this patient identifier, a password reset email has been sent.',
        })


class PatientPasswordResetVerifyView(APIView):
    """Verify a reset token before allowing a password to be chosen for a patient."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PatientPasswordResetVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reset_token = serializer.validated_data['reset_token']
        reset_token.verified_at = timezone.now()
        reset_token.save(update_fields=['verified_at'])
        return Response({'detail': 'Reset token verified. You can now choose a new password.'})


class PatientPasswordResetConfirmView(APIView):
    """Confirm password reset with token for a patient."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PatientPasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']
        
        patient = Patient.objects.filter(id=reset_token.user_id).first()
        
        if not patient:
            return Response({'error': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        patient.set_password(new_password)
        patient.save(update_fields=['password'])
        
        reset_token.is_used = True
        reset_token.save(update_fields=['is_used'])
        
        logger.info('Patient password reset successfully: patient_id=%s', patient.id)
        
        return Response({'detail': 'Password reset successfully. You can now log in with your new password.'})


class PatientPasswordChangeView(APIView):
    """Change password for authenticated patient."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Verify patient is authenticated and is a patient
        if not getattr(request.user, 'is_patient', False) and not isinstance(request.user, Patient):
            return Response({'error': 'Only authenticated patients can change their password.'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        serializer = PatientPasswordChangeSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        new_password = serializer.validated_data['new_password']
        patient = request.user
        
        patient.set_password(new_password)
        patient.save(update_fields=['password'])
        
        logger.info('Patient password changed successfully: patient_id=%s', patient.id)
        
        return Response({'detail': 'Password changed successfully.'})
