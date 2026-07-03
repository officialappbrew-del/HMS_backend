from django.db.models import Sum, Avg
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.views import TenantScopedModelViewSet
from .models import Budget, Forecast, Grant, BudgetVariance, BudgetReport
from .serializers import (
    BudgetSerializer,
    ForecastSerializer,
    GrantSerializer,
    BudgetVarianceSerializer,
    BudgetReportSerializer
)


class IsFinanceStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) in (
            'admin', 'superadmin', 'accountant', 'finance_officer'
        )


class BudgetViewSet(TenantScopedModelViewSet):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        department = self.request.query_params.get('department')
        year = self.request.query_params.get('year')
        status_filter = self.request.query_params.get('status')
        if department:
            qs = qs.filter(department=department)
        if year:
            qs = qs.filter(year=year)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        tenant = self.get_tenant()
        total_budget = Budget.objects.filter(tenant=tenant).aggregate(total=Sum('amount'))['total'] or 0
        total_utilized = Budget.objects.filter(tenant=tenant).aggregate(total=Sum('utilized'))['total'] or 0
        utilization_rate = round((float(total_utilized) / float(total_budget) * 100), 1) if total_budget > 0 else 0
        
        return Response({
            'total_budget': float(total_budget),
            'total_utilized': float(total_utilized),
            'utilization_rate': utilization_rate
        })


class ForecastViewSet(TenantScopedModelViewSet):
    queryset = Forecast.objects.all()
    serializer_class = ForecastSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        year = self.request.query_params.get('year')
        if category:
            qs = qs.filter(category=category)
        if year:
            qs = qs.filter(year=year)
        return qs


class GrantViewSet(TenantScopedModelViewSet):
    queryset = Grant.objects.all()
    serializer_class = GrantSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        donor = self.request.query_params.get('donor')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if donor:
            qs = qs.filter(donor__icontains=donor)
        return qs


class BudgetVarianceViewSet(TenantScopedModelViewSet):
    queryset = BudgetVariance.objects.all()
    serializer_class = BudgetVarianceSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get('year')
        period = self.request.query_params.get('period')
        if year:
            qs = qs.filter(year=year)
        if period:
            qs = qs.filter(period=period)
        return qs


class BudgetReportViewSet(TenantScopedModelViewSet):
    queryset = BudgetReport.objects.all()
    serializer_class = BudgetReportSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        report_type = self.request.query_params.get('report_type')
        if report_type:
            qs = qs.filter(report_type=report_type)
        return qs
