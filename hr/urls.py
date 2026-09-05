from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (AttendanceViewSet, HrEmployeeListView, HrSummaryView, LeaveApplicationViewSet,
                    PayrollRunViewSet, SalaryStructureViewSet)

router = DefaultRouter()
router.register('attendance', AttendanceViewSet, basename='hr-attendance')
router.register('leave-applications', LeaveApplicationViewSet, basename='hr-leave')
router.register('salary-structures', SalaryStructureViewSet, basename='hr-salary')
router.register('payroll-runs', PayrollRunViewSet, basename='hr-payroll')

urlpatterns = [
    path('summary/', HrSummaryView.as_view(), name='hr-summary'),
    path('employees/', HrEmployeeListView.as_view(), name='hr-employees'),
    path('', include(router.urls)),
]