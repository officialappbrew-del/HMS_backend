from django.db.models import Sum
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Invoice, Payment
from core.permissions import IsFinanceStaff
from core.views import TenantScopedModelViewSet
from .models import Account, Asset, JournalEntry, PurchaseOrder, TaxConfiguration, Vendor, VendorPayment
from .serializers import (AccountSerializer, AssetSerializer, JournalEntrySerializer, PurchaseOrderSerializer,
                           TaxConfigurationSerializer, VendorPaymentSerializer, VendorSerializer)


class AccountsSummaryView(APIView):
    permission_classes = [IsFinanceStaff]

    def get(self, request):
        tenant = getattr(request, 'tenant', None) or getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        invoices = Invoice.objects.filter(tenant=tenant)
        payments = Payment.objects.filter(tenant=tenant, status='completed')
        return Response({
            'invoice_count': invoices.count(),
            'outstanding_receivables': invoices.aggregate(total=Sum('balance_due'))['total'] or 0,
            'collected_amount': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'pending_journals': JournalEntry.objects.filter(tenant=tenant, status='draft').count(),
            'vendor_count': Vendor.objects.filter(tenant=tenant).count(),
            'purchase_order_count': PurchaseOrder.objects.filter(tenant=tenant).count(),
            'vendor_payment_count': VendorPayment.objects.filter(tenant=tenant).count(),
            'asset_count': Asset.objects.filter(tenant=tenant, status=Asset.Status.ACTIVE).count(),
        })


class AccountViewSet(TenantScopedModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class JournalEntryViewSet(TenantScopedModelViewSet):
    queryset = JournalEntry.objects.prefetch_related('lines')
    serializer_class = JournalEntrySerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant(), created_by=self.request.user)


class VendorViewSet(TenantScopedModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class PurchaseOrderViewSet(TenantScopedModelViewSet):
    queryset = PurchaseOrder.objects.select_related('vendor').prefetch_related('lines')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class VendorPaymentViewSet(TenantScopedModelViewSet):
    queryset = VendorPayment.objects.select_related('vendor')
    serializer_class = VendorPaymentSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class AssetViewSet(TenantScopedModelViewSet):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())


class TaxConfigurationViewSet(TenantScopedModelViewSet):
    queryset = TaxConfiguration.objects.all()
    serializer_class = TaxConfigurationSerializer
    permission_classes = [IsFinanceStaff]

    def perform_create(self, serializer):
        serializer.save(tenant=self._get_request_tenant())
