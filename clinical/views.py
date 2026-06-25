from django.db import transaction
from rest_framework import permissions, viewsets
from .models import ConsultationNote, Prescription, VitalSign
from .serializers import ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer
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
