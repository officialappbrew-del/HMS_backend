from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PatientViewSet, PatientVisitViewSet, AppointmentViewSet,
    patient_login, BulkPatientUploadViewSet
)

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'visits', PatientVisitViewSet, basename='visit')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'bulk-uploads', BulkPatientUploadViewSet, basename='bulk-upload')

urlpatterns = [
    path('login/', patient_login, name='patient-login'),
    path('', include(router.urls)),
]