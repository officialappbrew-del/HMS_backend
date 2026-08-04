from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet
from .models import (
    DutyRoster,
    DutyAssignment,
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

    @action(detail=False, methods=['get'], url_path='on-call')
    def on_call(self, request):
        """Return on-call and emergency-coverage staff for a given date (default: today).

        Query params:
          date       – ISO date string (YYYY-MM-DD). Defaults to today.
          department – optional department name filter (case-insensitive).
        """
        from datetime import date as date_cls

        query_date_str = request.query_params.get('date')
        department = request.query_params.get('department')

        try:
            query_date = date_cls.fromisoformat(query_date_str) if query_date_str else date_cls.today()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.get_queryset()
        if department:
            queryset = queryset.filter(department__icontains=department)

        assignments = DutyAssignment.objects.filter(
            roster__in=queryset,
            date=query_date,
        ).select_related('roster', 'staff_user').order_by('start_time', 'staff_name')

        on_call_types_lower = {
            'on call', 'call duty', 'night duty', 'emergency',
            'emergency cover', 'on-call', 'night',
        }

        all_shifts = []
        on_call_staff = []

        for assignment in assignments:
            entry = {
                'id': assignment.id,
                'staffId': assignment.staff_id,
                'staffName': assignment.staff_name,
                'dutyType': assignment.duty_type,
                'startTime': assignment.start_time.isoformat() if assignment.start_time else None,
                'endTime': assignment.end_time.isoformat() if assignment.end_time else None,
                'date': assignment.date.isoformat() if assignment.date else None,
                'notes': assignment.notes,
                'department': assignment.roster.department,
                'rosterId': assignment.roster.roster_id,
                'staffUserId': assignment.staff_user_id,
                'role': getattr(assignment.staff_user, 'role', '') if assignment.staff_user else '',
                'email': getattr(assignment.staff_user, 'email', '') if assignment.staff_user else '',
                'phone': getattr(assignment.staff_user, 'phone', '') if assignment.staff_user else '',
            }
            all_shifts.append(entry)

            if assignment.duty_type and assignment.duty_type.lower() in on_call_types_lower:
                on_call_staff.append(entry)

        # Sort on_call_staff by start time, then name
        on_call_staff.sort(key=lambda x: (x['startTime'] or '00:00', x['staffName'] or ''))

        return Response({
            'date': query_date.isoformat(),
            'on_call_staff': on_call_staff,
            'all_shifts': all_shifts,
        })


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

    def _get_approver_name(self, request):
        """Resolve the acting user's display name from the authenticated request."""
        approver = request.data.get('approvedBy') or request.data.get('approved_by')
        if approver:
            return approver
        user = request.user
        if user and not user.is_anonymous:
            full_name = getattr(user, 'get_full_name', None)
            if callable(full_name):
                name = full_name()
                if name:
                    return name
            return user.get_full_name() or user.username or user.email or 'System'
        return 'System'

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = 'Approved'
        leave_request.approved_by = self._get_approver_name(request)
        approval_date = request.data.get('approvalDate') or request.data.get('approval_date')
        leave_request.approval_date = approval_date or None
        leave_request.save(update_fields=['status', 'approved_by', 'approval_date', 'updated_at'])
        return Response(LeaveRequestSerializer(leave_request).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = 'Rejected'
        leave_request.approved_by = self._get_approver_name(request)
        approval_date = request.data.get('approvalDate') or request.data.get('approval_date')
        leave_request.approval_date = approval_date or None
        leave_request.save(update_fields=['status', 'approved_by', 'approval_date', 'updated_at'])
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

    def _get_approver_name(self, request):
        """Resolve the acting user's display name from the authenticated request."""
        approver = request.data.get('approvedBy') or request.data.get('approved_by')
        if approver:
            return approver
        user = request.user
        if user and not user.is_anonymous:
            full_name = getattr(user, 'get_full_name', None)
            if callable(full_name):
                name = full_name()
                if name:
                    return name
            return user.get_full_name() or user.username or user.email or 'System'
        return 'System'

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        record = self.get_object()
        record.status = 'Approved'
        record.approved_by = self._get_approver_name(request)
        approval_date = request.data.get('approvalDate') or request.data.get('approval_date')
        record.approval_date = approval_date or None
        record.save(update_fields=['status', 'approved_by', 'approval_date', 'updated_at'])
        return Response(OvertimeRecordSerializer(record).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        record = self.get_object()
        record.status = 'Rejected'
        record.approved_by = self._get_approver_name(request)
        approval_date = request.data.get('approvalDate') or request.data.get('approval_date')
        record.approval_date = approval_date or None
        record.save(update_fields=['status', 'approved_by', 'approval_date', 'updated_at'])
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
