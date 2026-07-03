from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.views import TenantScopedModelViewSet
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim, BillingAuditLog
from .serializers import (
    InvoiceSerializer,
    InvoiceSummarySerializer,
    PaymentSerializer,
    InsuranceClaimSerializer,
    BillingAuditLogSerializer
)


class IsBillingStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) in (
            'admin', 'superadmin', 'billing_officer', 'accountant', 'receptionist'
        )


class InvoiceViewSet(TenantScopedModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsBillingStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        patient_id = self.request.query_params.get('patient_id')
        status_filter = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if start_date:
            qs = qs.filter(invoice_date__date__gte=start_date)
        if end_date:
            qs = qs.filter(invoice_date__date__lte=end_date)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=serializer.instance,
            action='created',
            description=f"Invoice {serializer.instance.invoice_number} created",
            user=str(tenant_user) if tenant_user else str(user)
        )

    @action(detail=True, methods=['post'], url_path='issue')
    def issue_invoice(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = 'issued'
        invoice.save(update_fields=['status', 'updated_at'])
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=invoice,
            action='issued',
            description=f"Invoice {invoice.invoice_number} issued",
            user=str(request.user.tenant_user) if hasattr(request.user, 'tenant_user') else str(request.user)
        )
        return Response(InvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_invoice(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = 'cancelled'
        invoice.save(update_fields=['status', 'updated_at'])
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=invoice,
            action='cancelled',
            description=f"Invoice {invoice.invoice_number} cancelled",
            user=str(request.user.tenant_user) if hasattr(request.user, 'tenant_user') else str(request.user)
        )
        return Response(InvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        tenant = self.get_tenant()
        total_invoices = Invoice.objects.filter(tenant=tenant).count()
        total_revenue = Invoice.objects.filter(tenant=tenant).aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = Invoice.objects.filter(tenant=tenant).aggregate(total=Sum('amount_paid'))['total'] or 0
        total_pending = Invoice.objects.filter(tenant=tenant, status__in=['issued', 'partially_paid']).aggregate(
            total=Sum('balance_due')
        )['total'] or 0
        
        return Response({
            'total_invoices': total_invoices,
            'total_revenue': float(total_revenue),
            'total_paid': float(total_paid),
            'total_pending': float(total_pending),
            'collection_rate': round((float(total_paid) / float(total_revenue) * 100), 1) if total_revenue > 0 else 0
        })


class PaymentViewSet(TenantScopedModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsBillingStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        invoice_id = self.request.query_params.get('invoice_id')
        patient_id = self.request.query_params.get('patient_id')
        if invoice_id:
            qs = qs.filter(invoice__id=invoice_id)
        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        payment = serializer.instance
        invoice = payment.invoice
        
        invoice.amount_paid = invoice.payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
        invoice.balance_due = invoice.total_amount - invoice.amount_paid
        
        if invoice.balance_due <= 0:
            invoice.status = 'paid'
        elif invoice.amount_paid > 0:
            invoice.status = 'partially_paid'
        invoice.save()


class InsuranceClaimViewSet(TenantScopedModelViewSet):
    queryset = InsuranceClaim.objects.all()
    serializer_class = InsuranceClaimSerializer
    permission_classes = [IsBillingStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        patient_id = self.request.query_params.get('patient_id')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=serializer.instance.invoice,
            action='claim_submitted',
            description=f"Insurance claim {serializer.instance.claim_number} submitted to {serializer.instance.insurance_provider}",
            user=str(tenant_user) if tenant_user else str(user)
        )

    @action(detail=True, methods=['post'], url_path='submit')
    def submit_claim(self, request, pk=None):
        claim = self.get_object()
        claim.status = 'submitted'
        claim.submitted_date = timezone.now()
        claim.save(update_fields=['status', 'submitted_date', 'updated_at'])
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=claim.invoice,
            action='claim_submitted',
            description=f"Insurance claim {claim.claim_number} submitted",
            user=str(request.user.tenant_user) if hasattr(request.user, 'tenant_user') else str(request.user)
        )
        return Response(InsuranceClaimSerializer(claim, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_claim(self, request, pk=None):
        claim = self.get_object()
        approved_amount = request.data.get('approved_amount', claim.claimed_amount)
        claim.status = 'approved'
        claim.approved_amount = approved_amount
        claim.processed_date = timezone.now()
        claim.save(update_fields=['status', 'approved_amount', 'processed_date', 'updated_at'])
        
        invoice = claim.invoice
        invoice.insurance_amount = approved_amount
        invoice.patient_amount = invoice.total_amount - approved_amount
        invoice.save(update_fields=['insurance_amount', 'patient_amount', 'updated_at'])
        
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=claim.invoice,
            action='claim_approved',
            description=f"Insurance claim {claim.claim_number} approved for {approved_amount}",
            user=str(request.user.tenant_user) if hasattr(request.user, 'tenant_user') else str(request.user)
        )
        return Response(InsuranceClaimSerializer(claim, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_claim(self, request, pk=None):
        claim = self.get_object()
        rejection_reason = request.data.get('rejection_reason', '')
        claim.status = 'rejected'
        claim.rejection_reason = rejection_reason
        claim.processed_date = timezone.now()
        claim.save(update_fields=['status', 'rejection_reason', 'processed_date', 'updated_at'])
        BillingAuditLog.objects.create(
            tenant=self.get_tenant(),
            invoice=claim.invoice,
            action='claim_rejected',
            description=f"Insurance claim {claim.claim_number} rejected",
            user=str(request.user.tenant_user) if hasattr(request.user, 'tenant_user') else str(request.user)
        )
        return Response(InsuranceClaimSerializer(claim, context=self.get_serializer_context()).data)


class BillingAuditLogViewSet(TenantScopedModelViewSet):
    queryset = BillingAuditLog.objects.all()
    serializer_class = BillingAuditLogSerializer
    permission_classes = [IsBillingStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        invoice_id = self.request.query_params.get('invoice_id')
        action = self.request.query_params.get('action')
        if invoice_id:
            qs = qs.filter(invoice__id=invoice_id)
        if action:
            qs = qs.filter(action=action)
        return qs
