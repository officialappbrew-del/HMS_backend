from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InvoiceViewSet,
    PaymentViewSet,
    InsuranceClaimViewSet,
    BillingAuditLogViewSet,
)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'insurance-claims', InsuranceClaimViewSet)
router.register(r'audit-logs', BillingAuditLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
