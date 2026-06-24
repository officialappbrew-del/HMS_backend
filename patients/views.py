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
    PatientAllergy, PatientMedication, Appointment
)
from .serializers import (
    PatientSerializer, PatientVisitSerializer, PatientDocumentSerializer,
    PatientAllergySerializer, PatientMedicationSerializer, AppointmentSerializer,
    PatientSearchSerializer, AppointmentScheduleSerializer, PatientLoginSerializer
)
from tenants.models import TenantUser
from core.permissions import IsTenantAdmin, IsDoctor, IsNurse


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


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


class PatientViewSet(viewsets.ModelViewSet):
    """ViewSet for managing patients."""
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Get tenant from user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            
            # Apply filters
            queryset = Patient.objects.filter(tenant=tenant)
            
            # Search by various fields
            search = self.request.query_params.get('search')
            if search:
                queryset = queryset.filter(
                    Q(hospital_number__icontains=search) |
                    Q(nhis_number__icontains=search) |
                    Q(first_name__icontains=search) |
                    Q(last_name__icontains=search) |
                    Q(phone__icontains=search) |
                    Q(email__icontains=search)
                )
            
            # Filter by status
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(patient_status=status_filter)
            
            # Filter by gender
            gender_filter = self.request.query_params.get('gender')
            if gender_filter:
                queryset = queryset.filter(gender=gender_filter)
            
            return queryset
        
        return Patient.objects.none()
    
    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        
        # Get tenant from tenant_user if available
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        
        # Try to get tenant from request data
        if not tenant:
            tenant_id = self.request.data.get('tenant')
            if tenant_id:
                from tenants.models import Tenant
                try:
                    tenant = Tenant.objects.get(id=int(tenant_id))
                except (Tenant.DoesNotExist, ValueError):
                    pass
        
        if not tenant:
            raise permissions.PermissionDenied("Tenant is required")
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(
                tenant=tenant,
                registered_by=user.tenant_user
            )
        else:
            serializer.save(tenant=tenant)
    
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
            
            tenant = user.tenant_user.tenant
            filters = Q(tenant=tenant)
            
            # Add search criteria
            data = serializer.validated_data
            
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
            
            patients = Patient.objects.filter(filters)
            page = self.paginate_queryset(patients)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(patients, many=True)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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


class PatientVisitViewSet(viewsets.ModelViewSet):
    """ViewSet for managing patient visits."""
    serializer_class = PatientVisitSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            
            # Filter by visit status
            status_filter = self.request.query_params.get('status')
            if status_filter:
                return PatientVisit.objects.filter(tenant=tenant, visit_status=status_filter)
            
            # Filter by date
            date_filter = self.request.query_params.get('date')
            if date_filter:
                return PatientVisit.objects.filter(
                    tenant=tenant,
                    checkin_time__date=date_filter
                )
            
            # Filter by doctor
            doctor_filter = self.request.query_params.get('doctor_id')
            if doctor_filter:
                return PatientVisit.objects.filter(tenant=tenant, doctor_id=doctor_filter)
            
            return PatientVisit.objects.filter(tenant=tenant)
        
        return PatientVisit.objects.none()
    
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


class AppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing appointments."""
    serializer_class = AppointmentSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            
            # Filter by date range
            start_date = self.request.query_params.get('start_date')
            end_date = self.request.query_params.get('end_date')
            
            queryset = Appointment.objects.filter(tenant=tenant)
            
            if start_date and end_date:
                queryset = queryset.filter(
                    scheduled_date__gte=start_date,
                    scheduled_date__lte=end_date
                )
            
            # Filter by status
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            
            # Filter by doctor
            doctor_filter = self.request.query_params.get('doctor_id')
            if doctor_filter:
                queryset = queryset.filter(doctor_id=doctor_filter)
            
            return queryset.order_by('scheduled_date', 'scheduled_time')
        
        return Appointment.objects.none()
    
    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant
        if not tenant:
            raise permissions.PermissionDenied("Tenant is required")
        serializer.save(tenant=tenant)
    
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