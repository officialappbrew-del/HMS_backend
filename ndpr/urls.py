from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConsentRecordViewSet,
    DataSubjectRequestViewSet,
    DataBreachViewSet,
    NDPRAuditLogViewSet,
    ComplianceReportViewSet,
)

router = DefaultRouter()
router.register(r'consent-records', ConsentRecordViewSet, basename='consent-record')
router.register(r'data-requests', DataSubjectRequestViewSet, basename='data-subject-request')
router.register(r'data-breaches', DataBreachViewSet, basename='data-breach')
router.register(r'audit-logs', NDPRAuditLogViewSet, basename='ndpr-audit-log')
router.register(r'compliance-reports', ComplianceReportViewSet, basename='compliance-report')

urlpatterns = [
    path('', include(router.urls)),
]
