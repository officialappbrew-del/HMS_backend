from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClinicalAuditViewSet, QualityIndicatorViewSet,
    PeerReviewViewSet, MortalityReviewViewSet, ComplianceScoreViewSet
)

router = DefaultRouter()
router.register(r'audits', ClinicalAuditViewSet, basename='clinical-audit')
router.register(r'quality-indicators', QualityIndicatorViewSet, basename='quality-indicator')
router.register(r'peer-reviews', PeerReviewViewSet, basename='peer-review')
router.register(r'mortality-reviews', MortalityReviewViewSet, basename='mortality-review')
router.register(r'compliance-scores', ComplianceScoreViewSet, basename='compliance-score')

urlpatterns = [
    path('', include(router.urls)),
]
