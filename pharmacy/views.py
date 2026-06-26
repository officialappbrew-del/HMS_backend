from django.db import models, transaction
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Drug, Supplier, Sale, SaleItem, Dispense
from .serializers import DrugSerializer, SupplierSerializer, SaleSerializer, SaleCreateSerializer, DispenseSerializer
from core.permissions import IsPharmacist, IsPharmacistOrTenantAdmin


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """Base viewset that limits querysets to the current tenant."""

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant
        else:
            return self.queryset.none()
        return self.queryset.filter(tenant=tenant)

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant
        if not tenant:
            tenant_id = self.request.data.get('tenant')
            if tenant_id:
                from tenants.models import Tenant
                try:
                    try:
                        tenant = Tenant.objects.get(id=int(tenant_id))
                    except ValueError:
                        tenant = Tenant.objects.get(public_id=tenant_id)
                except (Tenant.DoesNotExist, ValueError):
                    pass
        if not tenant:
            raise permissions.PermissionDenied("Tenant context required.")
        serializer.save(tenant=tenant)


class DrugViewSet(TenantScopedModelViewSet):
    queryset = Drug.objects.all()
    serializer_class = DrugSerializer
    permission_classes = [IsPharmacistOrTenantAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        search = params.get('search')
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                drug_code__icontains=search
            ) | queryset.filter(
                generic_name__icontains=search
            ) | queryset.filter(
                brand_name__icontains=search
            ) | queryset.filter(
                nafdac_number__icontains=search
            )

        category = params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        stock_status = params.get('stock_status')
        if stock_status == 'low':
            queryset = queryset.filter(stock_quantity__lte=models.F('reorder_level'))
        elif stock_status == 'ok':
            queryset = queryset.filter(stock_quantity__gt=models.F('reorder_level'))

        expiry_status = params.get('expiry_status')
        if expiry_status == 'expired':
            queryset = queryset.filter(expiry_date__lt=timezone.now().date())
        elif expiry_status == 'expiring_soon':
            queryset = queryset.filter(expiry_date__gte=timezone.now().date(), expiry_date__lte=timezone.now().date() + timezone.timedelta(days=30))

        return queryset

    @action(detail=False, methods=['get'])
    def reorder_alerts(self, request):
        queryset = self.get_queryset().filter(stock_quantity__lte=models.F('reorder_level'))
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reorder(self, request, pk=None):
        drug = self.get_object()
        return Response({
            'message': f'Reorder initiated for {drug.name}.',
            'drug': drug.name,
            'reorder_level': drug.reorder_level,
        })

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        drug = self.get_object()
        quantity = request.data.get('quantity')
        batch_number = request.data.get('batch_number', '')
        expiry_date = request.data.get('expiry_date')

        if not quantity or int(quantity) <= 0:
            return Response({'error': 'Valid quantity is required.'}, status=400)

        drug.stock_quantity += int(quantity)
        drug.last_restocked = timezone.now().date()
        if batch_number:
            drug.batch_number = batch_number
        if expiry_date:
            drug.expiry_date = expiry_date
        drug.save(update_fields=['stock_quantity', 'last_restocked', 'batch_number', 'expiry_date'])

        return Response({
            'message': f'Restocked {quantity} units of {drug.name}.',
            'drug': drug.name,
            'new_stock': drug.stock_quantity,
        })


class SupplierViewSet(TenantScopedModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsPharmacistOrTenantAdmin]


class SaleViewSet(TenantScopedModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsPharmacistOrTenantAdmin]

    def get_serializer_class(self):
        if self.action == 'create':
            return SaleCreateSerializer
        return SaleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        payment_method = params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        payment_status = params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        date_from = params.get('date_from')
        if date_from:
            queryset = queryset.filter(sold_at__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            queryset = queryset.filter(sold_at__date__lte=date_to)

        return queryset.select_related('patient', 'sold_by').prefetch_related('items')

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None)
        if not tenant_user and hasattr(user, 'tenant') and user.tenant:
            tenant_user = user
        tenant = tenant_user.tenant if tenant_user else None

        if not tenant:
            raise permissions.PermissionDenied("Tenant context required.")

        sale = serializer.save(tenant=tenant, sold_by=tenant_user)

        for item_data in serializer.validated_data.get('items', []):
            drug = item_data['drug']
            quantity = item_data['quantity']

            if drug.stock_quantity < quantity:
                raise serializers.ValidationError(f'Insufficient stock for {drug.name}. Available: {drug.stock_quantity}')

            drug.stock_quantity -= quantity
            drug.save(update_fields=['stock_quantity'])

            SaleItem.objects.create(
                sale=sale,
                drug=drug,
                quantity=quantity,
                unit_price=item_data['unit_price'],
                total_price=item_data['unit_price'] * quantity
            )

        sale.total_amount = sum(item.total_price for item in sale.items.all()) - sale.discount + sale.tax
        sale.save(update_fields=['total_amount'])


class DispenseViewSet(TenantScopedModelViewSet):
    queryset = Dispense.objects.all()
    serializer_class = DispenseSerializer
    permission_classes = [IsPharmacist]

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None)
        if not tenant_user and hasattr(user, 'tenant') and user.tenant:
            tenant_user = user
        tenant = tenant_user.tenant if tenant_user else None

        drug = serializer.validated_data['drug']
        quantity = serializer.validated_data['quantity']

        if drug.stock_quantity < quantity:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(f'Insufficient stock for {drug.name}. Available: {drug.stock_quantity}')

        drug.stock_quantity -= quantity
        drug.save(update_fields=['stock_quantity'])

        prescription = serializer.validated_data.get('prescription')
        if prescription and prescription.status == 'prescribed':
            prescription.status = 'dispensed'
            prescription.dispensed_by = tenant_user
            prescription.dispensed_date = serializer.validated_data.get('dispensed_date') or timezone.now()
            prescription.save(update_fields=['status', 'dispensed_by', 'dispensed_date'])

        serializer.save(tenant=tenant, dispensed_by=tenant_user)

    def get_queryset(self):
        queryset = super().get_queryset()
        prescription_id = self.request.query_params.get('prescription')
        if prescription_id:
            queryset = queryset.filter(prescription_id=prescription_id)
        return queryset
