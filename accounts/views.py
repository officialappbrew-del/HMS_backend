from django.db.models import Sum
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Invoice, Payment
from core.permissions import IsFinanceStaff
from core.views import TenantScopedModelViewSet
from .models import Account, Asset, JournalEntry, PurchaseOrder, TaxConfiguration, Vendor, VendorPayment
from .serializers import (AccountSerializer, AssetSerializer, JournalEntrySerializer, PurchaseOrderSerializer,
                           TaxConfigurationSerializer, VendorPaymentSerializer, VendorSerializer)


def accounts_scope(queryset, request):
    tenant = getattr(request, 'tenant', None)
    if tenant:
        return queryset.filter(tenant=tenant)
    if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', None) in {'super_admin', 'system_admin'}:
        return queryset
    return queryset.none()


class AccountsSummaryView(APIView):
    permission_classes = [IsFinanceStaff]

    def get(self, request):
        try:
            tenant_user = getattr(request.user, 'tenant_user', None)
        except ObjectDoesNotExist:
            tenant_user = None
        tenant = getattr(request, 'tenant', None) or getattr(tenant_user, 'tenant', None)
        invoices = Invoice.objects.all()
        payments = Payment.objects.filter(status='completed')
        if tenant:
            invoices = invoices.filter(tenant=tenant)
            payments = payments.filter(tenant=tenant)
        elif not (getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', None) in {'super_admin', 'system_admin'}):
            invoices = invoices.none()
            payments = payments.none()
        journals = accounts_scope(JournalEntry.objects.all(), request)
        vendors = accounts_scope(Vendor.objects.all(), request)
        orders = accounts_scope(PurchaseOrder.objects.all(), request)
        vendor_payments = accounts_scope(VendorPayment.objects.all(), request)
        assets = accounts_scope(Asset.objects.filter(status=Asset.Status.ACTIVE), request)
        return Response({
            'invoice_count': invoices.count(),
            'outstanding_receivables': invoices.aggregate(total=Sum('balance_due'))['total'] or 0,
            'collected_amount': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'pending_journals': journals.filter(status='draft').count(),
            'vendor_count': vendors.count(),
            'purchase_order_count': orders.count(),
            'vendor_payment_count': vendor_payments.count(),
            'asset_count': assets.count(),
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
