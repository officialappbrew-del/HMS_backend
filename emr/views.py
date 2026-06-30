from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from clinical.views import TenantScopedModelViewSet, IsDoctorOrNurse
from .models import MedicalRecord, ProgressNote, ClinicalDocument, ProblemList, Allergy
from .serializers import (
    MedicalRecordSerializer, ProgressNoteSerializer,
    ClinicalDocumentSerializer, ProblemListSerializer, AllergySerializer
)


class MedicalRecordViewSet(TenantScopedModelViewSet):
    queryset = MedicalRecord.objects.all()
    serializer_class = MedicalRecordSerializer
    permission_classes = [IsDoctorOrNurse]

    @action(detail=True, methods=['post'], url_path='sign')
    def sign(self, request, pk=None):
        record = self.get_object()
        record.is_active = False
        record.closed_at = timezone.now()
        record.closed_by = request.user.tenant_user
        record.save(update_fields=['is_active', 'closed_at', 'closed_by'])
        return Response({'status': 'signed'})


class ProgressNoteViewSet(TenantScopedModelViewSet):
    queryset = ProgressNote.objects.all()
    serializer_class = ProgressNoteSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        record_id = self.request.query_params.get('medical_record')
        if record_id:
            qs = qs.filter(medical_record_id=record_id)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        author = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            author = user.tenant_user
        if not tenant:
            raise permissions.PermissionDenied("Tenant context required.")
        save_kwargs = {'tenant': tenant}
        if author:
            save_kwargs['author'] = author
        serializer.save(**save_kwargs)

    @action(detail=True, methods=['post'], url_path='sign')
    def sign(self, request, pk=None):
        note = self.get_object()
        note.is_signed = True
        note.signed_at = timezone.now()
        note.save(update_fields=['is_signed', 'signed_at'])
        return Response({'status': 'signed'})


class ClinicalDocumentViewSet(TenantScopedModelViewSet):
    queryset = ClinicalDocument.objects.all()
    serializer_class = ClinicalDocumentSerializer
    permission_classes = [IsDoctorOrNurse]


class ProblemListViewSet(TenantScopedModelViewSet):
    queryset = ProblemList.objects.all()
    serializer_class = ProblemListSerializer
    permission_classes = [IsDoctorOrNurse]

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        problem = self.get_object()
        problem.status = 'resolved'
        problem.resolved_at = timezone.now()
        problem.save(update_fields=['status', 'resolved_at'])
        return Response({'status': 'resolved'})


class AllergyViewSet(TenantScopedModelViewSet):
    queryset = Allergy.objects.all()
    serializer_class = AllergySerializer
    permission_classes = [IsDoctorOrNurse]
