from django.db import models, transaction
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Drug, Dispense
from .serializers import DrugSerializer, DispenseSerializer
from core.permissions import IsPharmacist, IsPharmacistOrTenantAdmin


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """Base viewset that limits querysets to the current tenant."""

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            return self.queryset.filter(tenant=tenant)
        return self.queryset.none()

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
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
            )

        category = params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        stock_status = params.get('stock_status')
        if stock_status == 'low':
            queryset = queryset.filter(stock_quantity__lte=models.F('reorder_level'))
        elif stock_status == 'ok':
            queryset = queryset.filter(stock_quantity__gt=models.F('reorder_level'))

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


class DispenseViewSet(TenantScopedModelViewSet):
    queryset = Dispense.objects.all()
    serializer_class = DispenseSerializer
    permission_classes = [IsPharmacist]

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None)
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