from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DrugViewSet, SupplierViewSet, SaleViewSet, DispenseViewSet

router = DefaultRouter()
router.register(r'drugs', DrugViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'dispenses', DispenseViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
