from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WardRoundViewSet, HandoverNoteViewSet, GrandRoundViewSet, WardViewSet, BedViewSet

router = DefaultRouter()
router.register(r'rounds', WardRoundViewSet, basename='ward-round')
router.register(r'handovers', HandoverNoteViewSet, basename='handover-note')
router.register(r'grand-rounds', GrandRoundViewSet, basename='grand-round')
router.register(r'wards', WardViewSet, basename='ward')
router.register(r'beds', BedViewSet, basename='bed')

urlpatterns = [
    path('', include(router.urls)),
]
