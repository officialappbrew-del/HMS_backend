from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import TenantScopedModelViewSet
from tenants.models import TenantUser
from .models import AttendanceRecord, LeaveApplication, PayrollLine, PayrollRun, SalaryStructure
from .serializers import (AttendanceRecordSerializer, EmployeeSummarySerializer, LeaveApplicationSerializer,
                           PayrollRunSerializer, SalaryStructureSerializer)


HR_ROLES = {'admin', 'tenant_admin', 'hr_manager', 'super_admin', 'system_admin'}


def current_role(request):
    return getattr(getattr(request.user, 'tenant_user', None), 'role', None) or getattr(request.user, 'role', None)


class IsHrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and current_role(request) in HR_ROLES)


class HrEmployeeListView(APIView):
    permission_classes = [IsHrStaff]

    def get(self, request):
        tenant = getattr(request, 'tenant', None) or getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        employees = TenantUser.objects.filter(tenant=tenant, employment_status__in=['active', 'on_leave']).select_related('department')
        return Response(EmployeeSummarySerializer(employees, many=True).data)


class HrSummaryView(APIView):
    permission_classes = [IsHrStaff]

    def get(self, request):
        tenant = getattr(request, 'tenant', None) or getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        attendance = AttendanceRecord.objects.filter(tenant=tenant)
        leaves = LeaveApplication.objects.filter(tenant=tenant)
        return Response({
            'staff_count': TenantUser.objects.filter(tenant=tenant, employment_status__in=['active', 'on_leave']).count(),
            'attendance': list(attendance.values('status').annotate(count=Count('id'))),
            'pending_leave_count': leaves.filter(status=LeaveApplication.Status.PENDING).count(),
            'approved_leave_count': leaves.filter(status=LeaveApplication.Status.APPROVED).count(),
            'late_count': attendance.filter(late_minutes__gt=0).count(),
        })


class AttendanceViewSet(TenantScopedModelViewSet):
    queryset = AttendanceRecord.objects.select_related('employee', 'employee__department')
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsHrStaff]
    filterset_fields = ['employee', 'date', 'status']

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant(), approved_by=self.request.user)


class LeaveApplicationViewSet(TenantScopedModelViewSet):
    queryset = LeaveApplication.objects.select_related('employee', 'employee__department')
    serializer_class = LeaveApplicationSerializer
    permission_classes = [IsHrStaff]
    filterset_fields = ['employee', 'leave_type', 'status']

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant(), employee_id=self.request.data.get('employee'))

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        leave = self.get_object()
        leave.status = LeaveApplication.Status.APPROVED
        leave.reviewed_by = request.user
        leave.review_reason = str(request.data.get('reason', '')).strip()
        leave.save(update_fields=['status', 'reviewed_by', 'review_reason', 'updated_at'])
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            return Response({'reason': 'A rejection reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        leave = self.get_object()
        leave.status = LeaveApplication.Status.REJECTED
        leave.reviewed_by = request.user
        leave.review_reason = reason
        leave.save(update_fields=['status', 'reviewed_by', 'review_reason', 'updated_at'])
        return Response(self.get_serializer(leave).data)


class SalaryStructureViewSet(TenantScopedModelViewSet):
    queryset = SalaryStructure.objects.select_related('employee')
    serializer_class = SalaryStructureSerializer
    permission_classes = [IsHrStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class PayrollRunViewSet(TenantScopedModelViewSet):
    queryset = PayrollRun.objects.prefetch_related('lines', 'lines__employee')
    serializer_class = PayrollRunSerializer
    permission_classes = [IsHrStaff]
    filterset_fields = ['month', 'status']

    def perform_create(self, serializer):
        tenant = self._get_request_tenant()
        with transaction.atomic():
            run = serializer.save(tenant=tenant, created_by=self.request.user)
            structures = SalaryStructure.objects.filter(tenant=tenant, employee__employment_status__in=['active', 'on_leave'])
            totals = [Decimal('0'), Decimal('0'), Decimal('0')]
            for structure in structures:
                allowances = sum((structure.housing_allowance, structure.transport_allowance,
                                  structure.medical_allowance, structure.other_allowance), Decimal('0'))
                gross = structure.basic_salary + allowances
                deductions = (structure.basic_salary * structure.pf_percentage / 100) + (gross * structure.esi_percentage / 100) + structure.professional_tax
                PayrollLine.objects.create(run=run, employee=structure.employee, basic_salary=structure.basic_salary,
                                           allowances=allowances, gross_salary=gross, deductions=deductions,
                                           net_salary=gross - deductions)
                totals[0] += gross
                totals[1] += deductions
                totals[2] += gross - deductions
            run.total_gross, run.total_deductions, run.total_net = totals
            run.status = PayrollRun.Status.READY
            run.save(update_fields=['total_gross', 'total_deductions', 'total_net', 'status', 'updated_at'])

