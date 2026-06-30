from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ConsultationNote, Prescription, VitalSign, EarlyWarningScore, VitalSignAlert
from .serializers import ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer, EarlyWarningScoreSerializer, VitalSignAlertSerializer
from core.permissions import IsDoctor, IsPharmacist, IsNurse


class IsDoctorOrPharmacist(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'doctor' or request.user.role == 'pharmacist'
        )


class IsDoctorOrNurse(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'doctor' or request.user.role == 'nurse'
        )


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """Base viewset that limits querysets to the current tenant."""

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            return self.queryset.filter(tenant=tenant)
        return self.queryset.none()

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        if not tenant:
            raise permissions.PermissionDenied("Tenant context required.")
        serializer.save(tenant=tenant)


class ConsultationNoteViewSet(TenantScopedModelViewSet):
    queryset = ConsultationNote.objects.all()
    serializer_class = ConsultationNoteSerializer
    permission_classes = [IsDoctor]

    def get_queryset(self):
        queryset = super().get_queryset()
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(doctor=user.tenant_user)


class PrescriptionViewSet(TenantScopedModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [IsDoctorOrPharmacist]

    def get_queryset(self):
        queryset = super().get_queryset()
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        prescription_status = self.request.query_params.get('status')
        if prescription_status:
            queryset = queryset.filter(status=prescription_status)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(prescribed_by=user.tenant_user)


class VitalSignViewSet(TenantScopedModelViewSet):
    queryset = VitalSign.objects.all()
    serializer_class = VitalSignSerializer
    permission_classes = [IsDoctorOrNurse]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(recorded_by=user.tenant_user)


class EarlyWarningScoreViewSet(TenantScopedModelViewSet):
    queryset = EarlyWarningScore.objects.all()
    serializer_class = EarlyWarningScoreSerializer
    permission_classes = [IsDoctorOrNurse]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(calculated_by=user.tenant_user)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """Calculate EWS from submitted vital signs without persisting."""
        data = request.data
        required = ['respiration_rate', 'oxygen_saturation', 'temperature', 'systolic_bp', 'heart_rate', 'consciousness']
        missing = [f for f in required if f not in data]
        if missing:
            return Response({'detail': f'Missing fields: {missing}'}, status=status.HTTP_400_BAD_REQUEST)
        
        result = EarlyWarningScore.calculate_newts2_score(
            respiration_rate=int(data['respiration_rate']),
            oxygen_saturation=float(data['oxygen_saturation']),
            temperature=float(data['temperature']),
            systolic_bp=int(data['systolic_bp']),
            heart_rate=int(data['heart_rate']),
            consciousness=data['consciousness']
        )
        return Response(result)


class VitalSignAlertViewSet(TenantScopedModelViewSet):
    queryset = VitalSignAlert.objects.all()
    serializer_class = VitalSignAlertSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        queryset = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        acknowledged = self.request.query_params.get('acknowledged')
        if acknowledged is not None:
            queryset = queryset.filter(acknowledged=acknowledged.lower() == 'true')
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            queryset = queryset.filter(resolved=resolved.lower() == 'true')
        return queryset

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.acknowledged = True
            alert.acknowledged_by = user.tenant_user
            alert.acknowledged_at = timezone.now()
            alert.save()
        return Response({'status': 'acknowledged'})

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.resolved = True
            alert.resolved_by = user.tenant_user
            alert.resolved_at = timezone.now()
            alert.resolution_notes = request.data.get('resolution_notes', '')
            alert.save()
        return Response({'status': 'resolved'})

    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        queryset = self.get_queryset().filter(resolved=False)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
