from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CountryViewSet, StateViewSet, LGAViewSet,
    FacilityTypeViewSet, SpecializationViewSet,
    LanguageViewSet, SystemSettingViewSet, AuditLogViewSet
)

router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='country')
router.register(r'states', StateViewSet, basename='state')
router.register(r'lgas', LGAViewSet, basename='lga')
router.register(r'facility-types', FacilityTypeViewSet, basename='facility-type')
router.register(r'specializations', SpecializationViewSet, basename='specialization')
router.register(r'languages', LanguageViewSet, basename='language')
router.register(r'system-settings', SystemSettingViewSet, basename='system-setting')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', include(router.urls)),
]