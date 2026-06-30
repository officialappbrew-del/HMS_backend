from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet, IsDoctorOrNurse
from .models import ClinicalAudit, QualityIndicator, PeerReview, MortalityReview, ComplianceScore
from .serializers import (
    ClinicalAuditSerializer, QualityIndicatorSerializer,
    PeerReviewSerializer, MortalityReviewSerializer, ComplianceScoreSerializer
)


class ClinicalAuditViewSet(TenantScopedModelViewSet):
    queryset = ClinicalAudit.objects.all()
    serializer_class = ClinicalAuditSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        audit_type = self.request.query_params.get('type')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if audit_type:
            qs = qs.filter(audit_type=audit_type)
        return qs

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        audit = self.get_object()
        audit.status = 'completed'
        audit.completion_date = timezone.now()
        audit.save(update_fields=['status', 'completion_date'])
        return Response({'status': 'completed'})

    @action(detail=True, methods=['post'], url_path='schedule-peer-review')
    def schedule_peer_review(self, request, pk=None):
        audit = self.get_object()
        peer_review = PeerReview.objects.create(
            tenant=audit.tenant,
            audit=audit,
            title=f"Peer Review: {audit.title}",
            scheduled_date=timezone.now() + timezone.timedelta(days=7),
            status='scheduled',
            reviewers=[],
            cases_count=0,
            recommendations_count=0,
        )
        return Response(PeerReviewSerializer(peer_review).data)


class QualityIndicatorViewSet(TenantScopedModelViewSet):
    queryset = QualityIndicator.objects.all()
    serializer_class = QualityIndicatorSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        if category:
            qs = qs.filter(category=category)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(description__icontains=search)
        return qs


class PeerReviewViewSet(TenantScopedModelViewSet):
    queryset = PeerReview.objects.all()
    serializer_class = PeerReviewSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        audit_id = self.request.query_params.get('audit')
        if audit_id:
            qs = qs.filter(audit_id=audit_id)
        return qs


class MortalityReviewViewSet(TenantScopedModelViewSet):
    queryset = MortalityReview.objects.all()
    serializer_class = MortalityReviewSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        department = self.request.query_params.get('department')
        if department:
            qs = qs.filter(department=department)
        return qs


class ComplianceScoreViewSet(TenantScopedModelViewSet):
    queryset = ComplianceScore.objects.all()
    serializer_class = ComplianceScoreSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        protocol = self.request.query_params.get('protocol')
        department = self.request.query_params.get('department')
        if protocol:
            qs = qs.filter(protocol=protocol)
        if department:
            qs = qs.filter(department=department)
        return qs
