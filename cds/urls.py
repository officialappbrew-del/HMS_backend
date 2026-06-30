from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DrugInteractionViewSet, AllergyCheckViewSet,
    DosingGuidelineViewSet, ClinicalGuidelineViewSet,
    RiskAssessmentViewSet, PatientAlertViewSet
)

router = DefaultRouter()
router.register(r'drug-interactions', DrugInteractionViewSet, basename='drug-interaction')
router.register(r'allergy-checks', AllergyCheckViewSet, basename='allergy-check')
router.register(r'dosing-guidelines', DosingGuidelineViewSet, basename='dosing-guideline')
router.register(r'clinical-guidelines', ClinicalGuidelineViewSet, basename='clinical-guideline')
router.register(r'risk-assessments', RiskAssessmentViewSet, basename='risk-assessment')
router.register(r'patient-alerts', PatientAlertViewSet, basename='patient-alert')

urlpatterns = [
    path('', include(router.urls)),
]
