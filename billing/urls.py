from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InvoiceViewSet,
    PaymentViewSet,
    InsuranceClaimViewSet,
    BillingAuditLogViewSet,
    SubscriptionOverviewView,
    SubscriptionCheckoutView,
    SubscriptionWebhookView,
    FinancialAnalyticsView,
    add_patient_charge,
    record_patient_payment,
)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'insurance-claims', InsuranceClaimViewSet)
router.register(r'audit-logs', BillingAuditLogViewSet)

urlpatterns = [
    path('patient-charges/', add_patient_charge, name='add-patient-charge'),
    path('patient-payments/', record_patient_payment, name='record-patient-payment'),
    path('subscription/', SubscriptionOverviewView.as_view(), name='subscription-overview'),
    path('checkout/', SubscriptionCheckoutView.as_view(), name='subscription-checkout'),
    path('webhook/', SubscriptionWebhookView.as_view(), name='subscription-webhook'),
    path('analytics/', FinancialAnalyticsView.as_view(), name='financial-analytics'),
    path('', include(router.urls)),
]
