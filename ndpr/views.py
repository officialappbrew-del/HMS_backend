from django.db.models import Count, Q, Sum, Avg, F
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet
from .models import ConsentRecord, DataSubjectRequest, DataBreach, NDPRAuditLog, ComplianceReport
from .serializers import (
    ConsentRecordSerializer,
    DataSubjectRequestSerializer,
    DataBreachSerializer,
    NDPRAuditLogSerializer,
    ComplianceReportSerializer,
)


class IsComplianceAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) in (
            'admin', 'superadmin', 'compliance_officer', 'data_protection_officer'
        )


class ConsentRecordViewSet(TenantScopedModelViewSet):
    queryset = ConsentRecord.objects.all()
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsComplianceAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        patient_id = self.request.query_params.get('patient_id')
        consent_type = self.request.query_params.get('consent_type')
        status_filter = self.request.query_params.get('status')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        if consent_type:
            qs = qs.filter(consent_type=consent_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=['post'], url_path='withdraw')
    def withdraw(self, request, pk=None):
        consent = self.get_object()
        reason = request.data.get('reason', '')
        consent.status = ConsentRecord.ConsentStatus.WITHDRAWN
        consent.withdrawal_reason = reason
        consent.withdrawn_at = timezone.now()
        consent.save(update_fields=['status', 'withdrawal_reason', 'withdrawn_at', 'updated_at'])
        return Response(ConsentRecordSerializer(consent, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='renew')
    def renew(self, request, pk=None):
        consent = self.get_object()
        retention = request.data.get('retentionPeriod') or consent.retention_period
        consent.status = ConsentRecord.ConsentStatus.ACTIVE
        consent.retention_period = retention
        if retention and retention not in ('indefinite', ''):
            try:
                years = int(retention.replace('_years', '').replace('_year', '').replace('treatment_period', '1'))
                consent.expiry_date = timezone.now().date() + __import__('datetime').timedelta(days=365 * years)
            except (ValueError, TypeError):
                consent.expiry_date = None
        else:
            consent.expiry_date = None
        consent.save(update_fields=['status', 'retention_period', 'expiry_date', 'updated_at'])
        return Response(ConsentRecordSerializer(consent, context=self.get_serializer_context()).data)


class DataSubjectRequestViewSet(TenantScopedModelViewSet):
    queryset = DataSubjectRequest.objects.all()
    serializer_class = DataSubjectRequestSerializer
    permission_classes = [IsComplianceAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        request_type = self.request.query_params.get('request_type')
        status_filter = self.request.query_params.get('status')
        urgency = self.request.query_params.get('urgency')
        if request_type:
            qs = qs.filter(request_type=request_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if urgency:
            qs = qs.filter(urgency=urgency)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        NDPRAuditLog.objects.create(
            tenant=self.get_tenant(),
            user=tenant_user,
            action=NDPRAuditLog.ActionType.DATA_REQUESTED,
            description=f"Data subject request created: {serializer.instance.request_type}",
            resource_type='DataSubjectRequest',
            resource_id=str(serializer.instance.id)
        )

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        dsr = self.get_object()
        dsr.status = DataSubjectRequest.RequestStatus.APPROVED
        dsr.processed_at = timezone.now()
        dsr.save(update_fields=['status', 'processed_at', 'updated_at'])
        return Response(DataSubjectRequestSerializer(dsr, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        dsr = self.get_object()
        dsr.status = DataSubjectRequest.RequestStatus.REJECTED
        dsr.processed_at = timezone.now()
        dsr.response = request.data.get('reason', '')
        dsr.save(update_fields=['status', 'processed_at', 'response', 'updated_at'])
        return Response(DataSubjectRequestSerializer(dsr, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        dsr = self.get_object()
        dsr.status = DataSubjectRequest.RequestStatus.COMPLETED
        dsr.completed_at = timezone.now()
        dsr.processed_at = dsr.processed_at or timezone.now()
        if dsr.submitted_at:
            delta = dsr.completed_at - dsr.submitted_at
            dsr.processing_time = f"{delta.days} days"
        dsr.save(update_fields=['status', 'completed_at', 'processed_at', 'processing_time', 'updated_at'])
        return Response(DataSubjectRequestSerializer(dsr, context=self.get_serializer_context()).data)


class DataBreachViewSet(TenantScopedModelViewSet):
    queryset = DataBreach.objects.all()
    serializer_class = DataBreachSerializer
    permission_classes = [IsComplianceAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        breach_type = self.request.query_params.get('breach_type')
        severity = self.request.query_params.get('severity')
        status_filter = self.request.query_params.get('status')
        if breach_type:
            qs = qs.filter(breach_type=breach_type)
        if severity:
            qs = qs.filter(severity=severity)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        NDPRAuditLog.objects.create(
            tenant=self.get_tenant(),
            user=tenant_user,
            action=NDPRAuditLog.ActionType.BREACH_REPORTED,
            description=f"Data breach reported: {serializer.instance.breach_type} affecting {serializer.instance.affected_individuals} individuals",
            resource_type='DataBreach',
            resource_id=str(serializer.instance.id)
        )

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        breach = self.get_object()
        new_status = request.data.get('status')
        if new_status not in DataBreach.BreachStatus.values:
            return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
        breach.status = new_status
        if new_status == DataBreach.BreachStatus.REPORTED:
            breach.reported_to_nitda = True
            breach.nitda_report_date = timezone.now()
        breach.save(update_fields=['status', 'reported_to_nitda', 'nitda_report_date', 'updated_at'])
        return Response(DataBreachSerializer(breach, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='notify')
    def notify(self, request, pk=None):
        breach = self.get_object()
        breach.notification_sent = True
        breach.notifications_sent_count = breach.affected_individuals
        breach.save(update_fields=['notification_sent', 'notifications_sent_count', 'updated_at'])
        return Response(DataBreachSerializer(breach, context=self.get_serializer_context()).data)


class NDPRAuditLogViewSet(TenantScopedModelViewSet):
    queryset = NDPRAuditLog.objects.all()
    serializer_class = NDPRAuditLogSerializer
    permission_classes = [IsComplianceAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        action_filter = self.request.query_params.get('action')
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if action_filter:
            qs = qs.filter(action=action_filter)
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        return qs


class ComplianceReportViewSet(TenantScopedModelViewSet):
    queryset = ComplianceReport.objects.all()
    serializer_class = ComplianceReportSerializer
    permission_classes = [IsComplianceAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        report_type = self.request.query_params.get('report_type')
        status_filter = self.request.query_params.get('status')
        if report_type:
            qs = qs.filter(report_type=report_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['get'], url_path='metrics')
    def metrics(self, request):
        tenant = self.get_tenant()
        total_consents = ConsentRecord.objects.filter(tenant=tenant).count()
        active_consents = ConsentRecord.objects.filter(tenant=tenant, status=ConsentRecord.ConsentStatus.ACTIVE).count()
        total_requests = DataSubjectRequest.objects.filter(tenant=tenant).count()
        pending_requests = DataSubjectRequest.objects.filter(tenant=tenant, status=DataSubjectRequest.RequestStatus.PENDING).count()
        completed_requests = DataSubjectRequest.objects.filter(tenant=tenant, status=DataSubjectRequest.RequestStatus.COMPLETED).count()
        total_breaches = DataBreach.objects.filter(tenant=tenant).count()
        open_breaches = DataBreach.objects.filter(tenant=tenant).exclude(status__in=[DataBreach.BreachStatus.RESOLVED, DataBreach.BreachStatus.REPORTED]).count()
        avg_response = DataBreach.objects.filter(tenant=tenant).aggregate(avg=Avg('response_time_hours'))['avg'] or 0.0
        training_count = 0
        consent_compliance = (active_consents / total_consents * 100) if total_consents > 0 else 100.0
        request_processing = (completed_requests / total_requests * 100) if total_requests > 0 else 100.0
        audit_compliance = 100.0
        return Response({
            'consentCompliance': round(consent_compliance, 1),
            'dataRequestsProcessed': round(request_processing, 1),
            'breachResponseTime': round(avg_response, 1),
            'auditCompliance': round(audit_compliance, 1),
            'trainingCompletion': round(training_count, 1),
            'totalConsents': total_consents,
            'activeConsents': active_consents,
            'expiredConsents': ConsentRecord.objects.filter(tenant=tenant, status=ConsentRecord.ConsentStatus.EXPIRED).count(),
            'withdrawnConsents': ConsentRecord.objects.filter(tenant=tenant, status=ConsentRecord.ConsentStatus.WITHDRAWN).count(),
            'totalRequests': total_requests,
            'pendingRequests': pending_requests,
            'openBreaches': open_breaches,
            'totalBreaches': total_breaches
        })
