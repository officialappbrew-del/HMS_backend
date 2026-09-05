from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (AccountViewSet, AccountsSummaryView, AssetViewSet, JournalEntryViewSet,
					PurchaseOrderViewSet, TaxConfigurationViewSet, VendorPaymentViewSet, VendorViewSet)

router = DefaultRouter()
router.register('chart-of-accounts', AccountViewSet, basename='account')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('vendors', VendorViewSet, basename='vendor')
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register('vendor-payments', VendorPaymentViewSet, basename='vendor-payment')
router.register('assets', AssetViewSet, basename='asset')
router.register('tax-configuration', TaxConfigurationViewSet, basename='tax-configuration')

urlpatterns = [path('summary/', AccountsSummaryView.as_view(), name='accounts-summary'), path('', include(router.urls))]