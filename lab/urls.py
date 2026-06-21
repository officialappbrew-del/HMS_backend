from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LabTestViewSet, LabOrderViewSet, LabResultViewSet, NCDCReportViewSet, InstrumentMaintenanceViewSet

router = DefaultRouter()
router.register(r'tests', LabTestViewSet)
router.register(r'orders', LabOrderViewSet)
router.register(r'results', LabResultViewSet)
router.register(r'ncdc-reports', NCDCReportViewSet)
router.register(r'instrument-maintenance', InstrumentMaintenanceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
