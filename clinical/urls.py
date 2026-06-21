from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ConsultationNoteViewSet, PrescriptionViewSet,
    VitalSignViewSet
)

router = DefaultRouter()
router.register(r'consultation-notes', ConsultationNoteViewSet, basename='consultation-note')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'vital-signs', VitalSignViewSet, basename='vital-sign')

urlpatterns = [
    path('', include(router.urls)),
]