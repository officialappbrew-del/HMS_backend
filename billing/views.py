import hashlib
import hmac
import json
from decimal import Decimal

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import TenantScopedModelViewSet
from core.permissions import IsFinanceStaff, IsTenantRootAdminOrGlobalAdmin
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim, BillingAuditLog
from tenants.models import Tenant, SubscriptionPayment, SubscriptionPlan
from pharmacy.models import Sale, SaleItem
from budgeting.models import Budget
from core.payment_settings import get_payment_setting, payment_setting_configured
from .serializers import (
    InvoiceSerializer,
    InvoiceSummarySerializer,
    PaymentSerializer,
    InsuranceClaimSerializer,
    BillingAuditLogSerializer
)


def _plan_amount(plan, billing_period):
    amounts = {
        'monthly': plan.price_monthly,
        'quarterly': plan.price_quarterly,
        'yearly': plan.price_yearly,
    }
    if billing_period not in amounts:
        raise ValueError('billing_period must be monthly, quarterly, or yearly')
    return Decimal(amounts[billing_period])


def _activate_subscription(payment):
    if payment.tenant is None:
        from tenants.views import _provision_paid_signup, _send_verification_email
        tenant, admin_user = _provision_paid_signup(payment)
        payment.tenant = tenant
        payment.save(update_fields=['tenant', 'updated_at'])
        _send_verification_email(tenant, admin_user)
    tenant = payment.tenant
    today = timezone.now().date()
    periods = {'monthly': 30, 'quarterly': 90, 'yearly': 365}
    tenant.subscription_plan = payment.plan
    tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
    tenant.subscription_start_date = today
    tenant.subscription_end_date = today + timezone.timedelta(days=periods[payment.billing_period])
    tenant.monthly_fee = payment.plan.price_monthly
    tenant.payment_method = payment.gateway
    tenant.save(update_fields=[
        'subscription_plan', 'subscription_status', 'subscription_start_date',
        'subscription_end_date', 'monthly_fee', 'payment_method', 'updated_at',
    ])


class SubscriptionOverviewView(APIView):
    """Return the current tenant subscription period for tenant administrators."""
    permission_classes = [IsTenantRootAdminOrGlobalAdmin]

    def get(self, request):
        tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        if tenant is None and getattr(request.user, 'role', None) in ('super_admin', 'system_admin'):
            tenant_id = request.query_params.get('tenant_id')
            tenant = Tenant.objects.filter(public_id=tenant_id, is_active=True).first()
        if tenant is None:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'tenant_id': str(tenant.public_id),
            'tenant_name': tenant.name,
            'subscription_status': tenant.subscription_status,
            'subscription_plan': tenant.subscription_plan_id,
            'subscription_plan_name': tenant.subscription_plan.name if tenant.subscription_plan else None,
            'subscription_start_date': tenant.subscription_start_date,
            'subscription_end_date': tenant.subscription_end_date,
            'days_remaining': tenant.days_remaining,
        })


class SubscriptionCheckoutView(APIView):
    """Initialize a Paystack checkout without activating the subscription."""
    permission_classes = [IsTenantRootAdminOrGlobalAdmin]

    def post(self, request):
        tenant = getattr(request, 'tenant', None)
        if not isinstance(tenant, Tenant) or getattr(request.user, 'role', None) in ('super_admin', 'system_admin') or getattr(request.user, 'is_superuser', False):
            tenant_id = request.data.get('tenant_id')
            if not tenant_id:
                return Response({'error': 'tenant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            tenant = Tenant.objects.filter(public_id=tenant_id, is_active=True).first()
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        plan = SubscriptionPlan.objects.filter(
            id=request.data.get('subscription_plan'), is_active=True
        ).first()
        if not plan:
            return Response({'error': 'Invalid subscription plan'}, status=status.HTTP_400_BAD_REQUEST)
        billing_period = request.data.get('billing_period', 'monthly')
        try:
            amount = _plan_amount(plan, billing_period)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({'error': 'This plan has no payable price'}, status=status.HTTP_400_BAD_REQUEST)
        if not payment_setting_configured('paystack_secret_key'):
            return Response({'error': 'Payment provider is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        reference = f"HMS-{tenant.public_id.hex[:12]}-{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
        payment = SubscriptionPayment.objects.create(
            tenant=tenant, plan=plan, reference=reference, amount=amount,
            currency=plan.currency, billing_period=billing_period,
        )
        try:
            response = requests.post(
                'https://api.paystack.co/transaction/initialize',
                headers={'Authorization': f"Bearer {get_payment_setting('paystack_secret_key')}"},
                json={
                    'email': tenant.billing_email or tenant.email,
                    'amount': int(amount * 100),
                    'currency': plan.currency,
                    'reference': reference,
                    'callback_url': f'{settings.FRONTEND_URL}/subscription?payment=complete',
                    'metadata': {'tenant_id': str(tenant.public_id), 'payment_id': payment.id},
                },
                timeout=15,
            )
            data = response.json()
            if not response.ok or not data.get('status'):
                raise requests.RequestException(data.get('message', 'Paystack initialization failed'))
        except (requests.RequestException, ValueError) as exc:
            payment.status = SubscriptionPayment.Status.FAILED
            payment.gateway_response = {'error': str(exc)}
            payment.save(update_fields=['status', 'gateway_response', 'updated_at'])
            return Response({'error': 'Unable to initialize payment'}, status=status.HTTP_502_BAD_GATEWAY)

        payment.gateway_response = data.get('data', {})
        payment.save(update_fields=['gateway_response', 'updated_at'])
        return Response({
            'reference': reference,
            'authorization_url': data['data']['authorization_url'],
            'access_code': data['data']['access_code'],
            'amount': str(amount),
            'currency': plan.currency,
        }, status=status.HTTP_201_CREATED)


class SubscriptionWebhookView(APIView):
    """Process Paystack or PayPal events exactly once."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if request.headers.get('x-paypal-transmission-id'):
            return self._handle_paypal(request)
        return self._handle_paystack(request)

    def _handle_paystack(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        expected = hmac.new(
            get_payment_setting('paystack_secret_key').encode(), request.body, hashlib.sha512
        ).hexdigest()
        if not payment_setting_configured('paystack_secret_key') or not hmac.compare_digest(signature, expected):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            event = json.loads(request.body)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
        if event.get('event') != 'charge.success':
            return Response({'detail': 'Event ignored'})

        data = event.get('data', {})
        reference = data.get('reference')
        with transaction.atomic():
            payment = SubscriptionPayment.objects.select_for_update().filter(reference=reference).first()
            if not payment:
                return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            if payment.status == SubscriptionPayment.Status.SUCCESS:
                return Response({'detail': 'Already processed'})
            expected_amount = int(payment.amount * 100)
            if data.get('amount') != expected_amount or data.get('currency') != payment.currency:
                payment.status = SubscriptionPayment.Status.FAILED
                payment.gateway_response = data
                payment.save(update_fields=['status', 'gateway_response', 'updated_at'])
                return Response({'error': 'Payment amount or currency mismatch'}, status=status.HTTP_400_BAD_REQUEST)
            payment.status = SubscriptionPayment.Status.SUCCESS
            payment.paid_at = timezone.now()
            payment.gateway_response = data
            payment.save(update_fields=['status', 'paid_at', 'gateway_response', 'updated_at'])
            _activate_subscription(payment)
        return Response({'detail': 'Payment processed'})

    def _handle_paypal(self, request):
        if not payment_setting_configured('paypal_webhook_id'):
            return Response({'error': 'PayPal webhook is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            token_response = requests.post(
                f"{get_payment_setting('paypal_base_url', 'https://api-m.sandbox.paypal.com')}/v1/oauth2/token",
                auth=(get_payment_setting('paypal_client_id'), get_payment_setting('paypal_client_secret')),
                data={'grant_type': 'client_credentials'},
                timeout=15,
            )
            token_response.raise_for_status()
            token = token_response.json()['access_token']
            verify_response = requests.post(
                f"{get_payment_setting('paypal_base_url', 'https://api-m.sandbox.paypal.com')}/v1/notifications/verify-webhook-signature",
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    'auth_algo': request.headers.get('x-paypal-auth-algo'),
                    'cert_url': request.headers.get('x-paypal-cert-url'),
                    'transmission_id': request.headers.get('x-paypal-transmission-id'),
                    'transmission_sig': request.headers.get('x-paypal-transmission-sig'),
                    'transmission_time': request.headers.get('x-paypal-transmission-time'),
                    'webhook_id': get_payment_setting('paypal_webhook_id'),
                    'webhook_event': request.data,
                },
                timeout=15,
            )
            verify_response.raise_for_status()
            if verify_response.json().get('verification_status') != 'SUCCESS':
                return Response({'error': 'Invalid PayPal webhook'}, status=status.HTTP_401_UNAUTHORIZED)
        except requests.RequestException:
            return Response({'error': 'Unable to verify PayPal webhook'}, status=status.HTTP_502_BAD_GATEWAY)

        event_type = request.data.get('event_type')
        if event_type == 'CHECKOUT.ORDER.APPROVED':
            order_id = request.data.get('resource', {}).get('id')
            try:
                capture_response = requests.post(
                    f"{get_payment_setting('paypal_base_url', 'https://api-m.sandbox.paypal.com')}/v2/checkout/orders/{order_id}/capture",
                    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                    timeout=15,
                )
                capture_response.raise_for_status()
            except requests.RequestException:
                return Response({'error': 'Unable to capture PayPal payment'}, status=status.HTTP_502_BAD_GATEWAY)
            return Response({'detail': 'PayPal payment capture requested'})
        if event_type not in {'CHECKOUT.ORDER.COMPLETED', 'PAYMENT.CAPTURE.COMPLETED'}:
            return Response({'detail': 'Event ignored'})

        resource = request.data.get('resource', {})
        reference = resource.get('custom_id')
        if not reference:
            reference = (resource.get('purchase_units') or [{}])[0].get('custom_id')
        order_id = (resource.get('supplementary_data', {}).get('related_ids', {}).get('order_id')
                    if resource else None)
        payment = SubscriptionPayment.objects.filter(reference=reference).first() if reference else None
        if payment is None and order_id:
            payment = SubscriptionPayment.objects.filter(gateway_response__id=order_id).first()
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == SubscriptionPayment.Status.SUCCESS:
            return Response({'detail': 'Already processed'})

        amount = None
        currency = None
        if resource.get('purchase_units'):
            unit = resource['purchase_units'][0]
            amount_data = unit.get('amount', {})
            amount, currency = amount_data.get('value'), amount_data.get('currency_code')
        elif resource.get('amount'):
            amount, currency = resource['amount'].get('value'), resource['amount'].get('currency_code')
        if Decimal(str(amount)) != payment.amount or currency != payment.currency:
            return Response({'error': 'Payment amount or currency mismatch'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            payment = SubscriptionPayment.objects.select_for_update().get(id=payment.id)
            payment.status = SubscriptionPayment.Status.SUCCESS
            payment.paid_at = timezone.now()
            payment.gateway_response = request.data
            payment.save(update_fields=['status', 'paid_at', 'gateway_response', 'updated_at'])
            _activate_subscription(payment)
        return Response({'detail': 'Payment processed'})


class InvoiceViewSet(TenantScopedModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset().select_related('patient', 'visit').prefetch_related('items', 'payments', 'claims')
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
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset().select_related('patient', 'invoice')
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
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset().select_related('patient', 'invoice')
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
    permission_classes = [IsFinanceStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        invoice_id = self.request.query_params.get('invoice_id')
        action = self.request.query_params.get('action')
        if invoice_id:
            qs = qs.filter(invoice__id=invoice_id)
        if action:
            qs = qs.filter(action=action)
        return qs


class FinancialAnalyticsView(APIView):
    """Comprehensive financial analytics for the tenant."""
    permission_classes = [IsFinanceStaff]

    def get(self, request):
        tenant = self.get_tenant()
        date_range = request.query_params.get('date_range', '30d')
        
        # Calculate date filter
        now = timezone.now()
        if date_range == '7d':
            start_date = now - timezone.timedelta(days=7)
        elif date_range == '30d':
            start_date = now - timezone.timedelta(days=30)
        elif date_range == '90d':
            start_date = now - timezone.timedelta(days=90)
        elif date_range == '1y':
            start_date = now - timezone.timedelta(days=365)
        else:
            start_date = now - timezone.timedelta(days=30)

        # Revenue from invoices
        invoices = Invoice.objects.filter(tenant=tenant, invoice_date__gte=start_date)
        total_revenue = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
        total_pending = invoices.filter(status__in=['issued', 'partially_paid']).aggregate(
            total=Sum('balance_due')
        )['total'] or 0

        # Revenue breakdown by payment method from pharmacy sales
        sales = Sale.objects.filter(tenant=tenant, sold_at__gte=start_date, status='completed')
        nhis_revenue = sales.filter(payment_method='nhis').aggregate(total=Sum('total_amount'))['total'] or 0
        private_revenue = sales.filter(payment_method='private').aggregate(total=Sum('total_amount'))['total'] or 0
        corporate_revenue = sales.filter(payment_method='corporate').aggregate(total=Sum('total_amount'))['total'] or 0
        cash_revenue = sales.filter(payment_method='cash').aggregate(total=Sum('total_amount'))['total'] or 0
        card_revenue = sales.filter(payment_method='card').aggregate(total=Sum('total_amount'))['total'] or 0
        transfer_revenue = sales.filter(payment_method='transfer').aggregate(total=Sum('total_amount'))['total'] or 0

        # Map payment methods to categories
        revenue_breakdown = {
            'nhis': float(nhis_revenue),
            'private': float(private_revenue) + float(cash_revenue) + float(card_revenue),
            'corporate': float(corporate_revenue),
            'out_of_pocket': float(cash_revenue),
        }

        # Cost breakdown
        # Staff costs - from payroll if available, otherwise estimate from active staff
        from staff.models import Staff
        active_staff_count = Staff.objects.filter(tenant=tenant, is_active=True).count()
        avg_salary = 250000  # Average monthly salary in Naira
        staff_costs = active_staff_count * avg_salary

        # Drug costs - from pharmacy sales
        drug_sales = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        drug_costs = float(drug_sales) * 0.6  # Estimate 60% of sales as cost

        # Equipment costs - from equipment maintenance
        from equipment.models import Equipment, MaintenanceRecord
        equipment_maintenance = MaintenanceRecord.objects.filter(
            tenant=tenant, date__gte=start_date
        ).aggregate(total=Sum('cost'))['total'] or 0
        equipment_costs = float(equipment_maintenance)

        # Overhead costs - estimate from tenant settings
        tenant_obj = tenant
        overhead_costs = float(tenant_obj.email_service_cost_monthly or 0) + float(tenant_obj.sms_service_cost_monthly or 0)
        overhead_costs = overhead_costs * 3  # Rough quarterly estimate

        # Maintenance costs
        maintenance_costs = float(equipment_maintenance) * 0.5

        cost_breakdown = {
            'staff': staff_costs,
            'drugs': drug_costs,
            'equipment': equipment_costs,
            'overhead': overhead_costs,
            'maintenance': maintenance_costs,
        }
        total_costs = sum(cost_breakdown.values())

        # Budgets
        budgets = Budget.objects.filter(tenant=tenant, year=now.year)
        budget_data = []
        for budget in budgets:
            budget_data.append({
                'id': str(budget.id),
                'department': budget.department,
                'category': budget.category,
                'amount': float(budget.amount),
                'utilized': float(budget.utilized),
                'period': budget.period,
                'year': budget.year,
                'variance': budget.variance,
            })

        # KPIs
        total_beds = 50  # Placeholder - should come from bed allocation
        bed_occupancy = 87  # Placeholder - should be computed from admissions
        avg_length_of_stay = 4.2  # Placeholder
        patient_satisfaction = 94  # Placeholder
        readmission_rate = 3.1  # Placeholder

        kpis = {
            'clinical': {
                'bedOccupancyRate': bed_occupancy,
                'averageLengthOfStay': avg_length_of_stay,
                'patientSatisfaction': patient_satisfaction,
                'readmissionRate': readmission_rate,
            },
            'financial': {
                'revenuePerBed': total_revenue / total_beds if total_beds > 0 else 0,
                'costPerPatient': total_costs / max(invoices.count(), 1),
                'operatingMargin': ((total_revenue - total_costs) / total_revenue * 100) if total_revenue > 0 else 0,
                'roi': 24.3,  # Placeholder
                'debtToEquityRatio': 0.3,  # Placeholder
            },
            'operational': {
                'averageWaitTime': 23,  # Placeholder
                'staffProductivity': 92,  # Placeholder
                'equipmentUtilization': 78,  # Placeholder
                'errorRate': 0.8,  # Placeholder
            }
        }

        # Cash flow
        cash_position = total_paid - total_costs
        cash_flow = {
            'operating': float(total_paid),
            'investing': -float(equipment_costs),
            'financing': 0,
            'net': cash_position,
        }

        return Response({
            'stats': {
                'totalRevenue': float(total_revenue),
                'totalCosts': float(total_costs),
                'netProfit': float(total_revenue - total_costs),
                'profitMargin': (float(total_revenue - total_costs) / float(total_revenue) * 100) if total_revenue > 0 else 0,
                'cashPosition': float(cash_position),
            },
            'revenue': revenue_breakdown,
            'costs': cost_breakdown,
            'budgets': budget_data,
            'kpis': kpis,
            'cashFlow': cash_flow,
            'invoices': {
                'total': invoices.count(),
                'paid': invoices.filter(status='paid').count(),
                'pending': invoices.filter(status__in=['issued', 'partially_paid']).count(),
            }
        })

    def get_tenant(self):
        user = self.request.user
        try:
            tenant_user = getattr(user, 'tenant_user', None)
            tenant = getattr(tenant_user, 'tenant', None)
            if tenant:
                return tenant
        except ObjectDoesNotExist:
            pass
        return None
