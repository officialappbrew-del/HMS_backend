from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DrugViewSet, DispenseViewSet

router = DefaultRouter()
router.register(r'drugs', DrugViewSet)
router.register(r'dispenses', DispenseViewSet)

urlpatterns = [
    path('', include(router.urls)),
]