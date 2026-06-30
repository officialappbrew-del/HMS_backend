from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ConsultationNoteViewSet, PrescriptionViewSet,
    VitalSignViewSet, EarlyWarningScoreViewSet, VitalSignAlertViewSet
)

router = DefaultRouter()
router.register(r'consultation-notes', ConsultationNoteViewSet, basename='consultation-note')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'vital-signs', VitalSignViewSet, basename='vital-sign')
router.register(r'early-warning-scores', EarlyWarningScoreViewSet, basename='early-warning-score')
router.register(r'vital-sign-alerts', VitalSignAlertViewSet, basename='vital-sign-alert')

urlpatterns = [
    path('', include(router.urls)),
]