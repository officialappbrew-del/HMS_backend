from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PatientViewSet, PatientVisitViewSet, AppointmentViewSet,
    patient_login, BulkPatientUploadViewSet,
    PatientPasswordResetRequestView, PatientPasswordResetVerifyView,
    PatientPasswordResetConfirmView, PatientPasswordChangeView
)

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'visits', PatientVisitViewSet, basename='visit')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'bulk-uploads', BulkPatientUploadViewSet, basename='bulk-upload')

urlpatterns = [
    path('login/', patient_login, name='patient-login'),
    path('password-reset/', PatientPasswordResetRequestView.as_view(), name='patient-password-reset-request'),
    path('password-reset/verify/', PatientPasswordResetVerifyView.as_view(), name='patient-password-reset-verify'),
    path('password-reset/confirm/', PatientPasswordResetConfirmView.as_view(), name='patient-password-reset-confirm'),
    path('password-change/', PatientPasswordChangeView.as_view(), name='patient-password-change'),
    path('', include(router.urls)),
]