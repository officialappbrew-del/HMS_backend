import csv
import time
import threading
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Patient, PatientVisit, PatientDocument,
    PatientAllergy, PatientMedication, Appointment,
    BulkPatientUpload
)
from .serializers import (
    PatientSerializer, PatientVisitSerializer, PatientDocumentSerializer,
    PatientAllergySerializer, PatientMedicationSerializer, AppointmentSerializer,
    PatientSearchSerializer, AppointmentScheduleSerializer, PatientLoginSerializer,
    BulkPatientUploadSerializer
)
from tenants.models import TenantUser
from core.views import TenantScopedModelViewSet
from core.models import AuditLog

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
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def patient_login(request):
    """Allow a patient to log in using their patient identifier and password."""
    serializer = PatientLoginSerializer(data=request.data)
    if serializer.is_valid():
        patient = serializer.validated_data['patient']
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
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        search = self.request.query_params.get('search')
        if search:
            search = search.strip()
            filters = (
                Q(hospital_number__icontains=search) |
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
        queryset = super().get_queryset()
        
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
        """End consultation."""
        visit = self.get_object()
        
        # Check permissions
        user = request.user
        if not hasattr(user, 'tenant_user') or user.tenant_user.role != 'doctor':
            raise permissions.PermissionDenied("Only doctors can end consultations")
        
        # End consultation
        visit.chief_complaint = request.data.get('chief_complaint', visit.chief_complaint)
        visit.history_of_present_illness = request.data.get('history_of_present_illness', visit.history_of_present_illness)
        visit.referral_from = request.data.get('referral_from', visit.referral_from)
        visit.referral_reason = request.data.get('referral_reason', visit.referral_reason)
        visit.consultation_end_time = timezone.now()
        visit.visit_status = request.data.get('next_status', 'awaiting_lab')
        visit.save()

        # Add or update consultation notes
        from clinical.models import ConsultationNote, Prescription
        consultation_note, created = ConsultationNote.objects.update_or_create(
            visit=visit,
            defaults={
                'tenant': visit.tenant,
                'patient': visit.patient,
                'doctor': user.tenant_user,
                'subjective': request.data.get('subjective', ''),
                'objective': request.data.get('objective', ''),
                'assessment': request.data.get('assessment', ''),
                'plan': request.data.get('plan', ''),
                'diagnosis_codes': request.data.get('diagnosis_codes', []),
                'differential_diagnosis': request.data.get('differential_diagnosis', ''),
                'is_final': request.data.get('is_final', True)
            }
        )

        # Create any prescriptions from submitted payload
        prescriptions = request.data.get('prescriptions', [])
        for prescription_data in prescriptions:
            Prescription.objects.create(
                tenant=visit.tenant,
                visit=visit,
                patient=visit.patient,
                prescribed_by=user.tenant_user,
                drug_name=prescription_data.get('drug_name', prescription_data.get('medication', '')),
                dosage=prescription_data.get('dosage', prescription_data.get('dose', '')),
                frequency=prescription_data.get('frequency', ''),
                duration=prescription_data.get('duration', 0) or 0,
                route=prescription_data.get('route', 'oral'),
                instructions=prescription_data.get('instructions', ''),
                special_instructions=prescription_data.get('special_instructions', ''),
                status=prescription_data.get('status', 'prescribed')
            )

        # Persist laboratory orders requested during consultation
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
                    status=order_data.get('status', 'ordered'),
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
                    description=(f"Priority: {order_data.get('priority', 'routine')}\n" + order_data.get('notes', '')).strip(),
                    uploaded_by=user.tenant_user,
                    document_date=timezone.now().date()
                )
            for index, order_data in enumerate(procedure_orders, start=1):
                PatientDocument.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    document_type='other',
                    title=f"Procedure: {order_data.get('procedure', 'Procedure order')}",
                    description=(f"Priority: {order_data.get('priority', 'routine')}\n" + order_data.get('notes', '')).strip(),
                    uploaded_by=user.tenant_user,
                    document_date=timezone.now().date()
                )
            for index, order_data in enumerate(referral_orders, start=1):
                PatientDocument.objects.create(
                    tenant=visit.tenant,
                    patient=visit.patient,
                    document_type='referral',
                    title=order_data.get('referral', f'Referral order {index}') ,
                    description=(f"Priority: {order_data.get('priority', 'routine')}\n" + order_data.get('notes', '')).strip(),
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
            # A lightweight invoice item list may be added here if the model supports it.

        serializer = self.get_serializer(visit)
        return Response(serializer.data)


class AppointmentViewSet(TenantScopedModelViewSet):
    """ViewSet for managing appointments."""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
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
                department_id=data.get('department_id'),
                appointment_type=data['appointment_type'],
                scheduled_date=data['scheduled_date'],
                scheduled_time=data['scheduled_time'],
                reason=data.get('reason', ''),
                notes=data.get('notes', '')
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
        
        # TODO: Send confirmation notification
        
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
                            'next_of_kin_phone': (row.get('next_of_kin_phone') or row.get('Next of Kin Phone') or '').strip(),
                            'next_of_kin_address': (row.get('next_of_kin_address') or row.get('Next of Kin Address') or '').strip(),
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
                            Patient.objects.create(tenant=upload.tenant, **validated_data)
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