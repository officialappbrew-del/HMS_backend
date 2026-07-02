from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet
from .models import (
    DutyRoster,
    LeaveRequest,
    OvertimeRecord,
    PerformanceAppraisal,
    PerformanceAudit,
    ResearchOutput,
    TeachingActivity,
    SatisfactionSurvey,
    PerformanceIncident,
)
from .serializers import (
    DutyRosterSerializer,
    LeaveRequestSerializer,
    OvertimeRecordSerializer,
    PerformanceAppraisalSerializer,
    PerformanceAuditSerializer,
    ResearchOutputSerializer,
    TeachingActivitySerializer,
    SatisfactionSurveySerializer,
    PerformanceIncidentSerializer,
)


class DutyRosterViewSet(TenantScopedModelViewSet):
    queryset = DutyRoster.objects.all()
    serializer_class = DutyRosterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department__icontains=department)
        return queryset

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        roster = self.get_object()
        roster.status = 'Published'
        roster.save(update_fields=['status', 'updated_at'])
        return Response(DutyRosterSerializer(roster).data)


class LeaveRequestViewSet(TenantScopedModelViewSet):
    queryset = LeaveRequest.objects.all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = 'Approved'
        leave_request.approved_by = request.data.get('approvedBy') or request.user.get_full_name() or 'System'
        leave_request.approval_date = request.data.get('approvalDate') or None
        leave_request.save(update_fields=['status', 'approved_by', 'approval_date', 'updated_at'])
        return Response(LeaveRequestSerializer(leave_request).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = 'Rejected'
        leave_request.approved_by = request.data.get('approvedBy') or 'System'
        leave_request.save(update_fields=['status', 'approved_by', 'updated_at'])
        return Response(LeaveRequestSerializer(leave_request).data)


class OvertimeRecordViewSet(TenantScopedModelViewSet):
    queryset = OvertimeRecord.objects.all()
    serializer_class = OvertimeRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        record = self.get_object()
        record.status = 'Approved'
        record.approved_by = request.data.get('approvedBy') or 'System'
        record.save(update_fields=['status', 'approved_by', 'updated_at'])
        return Response(OvertimeRecordSerializer(record).data)


class PerformanceAppraisalViewSet(TenantScopedModelViewSet):
    queryset = PerformanceAppraisal.objects.all()
    serializer_class = PerformanceAppraisalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_id = self.request.query_params.get('staff_id')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        return queryset


class PerformanceAuditViewSet(TenantScopedModelViewSet):
    queryset = PerformanceAudit.objects.all()
    serializer_class = PerformanceAuditSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department__icontains=department)
        return queryset


class ResearchOutputViewSet(TenantScopedModelViewSet):
    queryset = ResearchOutput.objects.all()
    serializer_class = ResearchOutputSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_id = self.request.query_params.get('staff_id')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        return queryset


class TeachingActivityViewSet(TenantScopedModelViewSet):
    queryset = TeachingActivity.objects.all()
    serializer_class = TeachingActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_id = self.request.query_params.get('staff_id')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        return queryset


class SatisfactionSurveyViewSet(TenantScopedModelViewSet):
    queryset = SatisfactionSurvey.objects.all()
    serializer_class = SatisfactionSurveySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_id = self.request.query_params.get('staff_id')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        return queryset


class PerformanceIncidentViewSet(TenantScopedModelViewSet):
    queryset = PerformanceIncident.objects.all()
    serializer_class = PerformanceIncidentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        staff_id = self.request.query_params.get('staff_id')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        return queryset
