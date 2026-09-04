import hashlib
import hmac
import json
from decimal import Decimal

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db import connection
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.utils import timezone
from patients.models import Patient
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import TenantScopedModelViewSet
from core.permissions import IsFinanceStaff, IsTenantRootAdminOrGlobalAdmin
from core.permissions import IsClinicalStaff
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim, BillingAuditLog
from tenants.models import Tenant, SubscriptionPayment, SubscriptionPlan, SUBSCRIPTION_PERIOD_MONTHS
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


class IsPatientBillingStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if getattr(user, 'is_patient', False):
            return bool(user.is_authenticated)
        tenant_user = getattr(user, 'tenant_user', None)
        role = getattr(tenant_user, 'role', None) or getattr(user, 'role', None)
        return bool(user.is_authenticated and role in {
            'admin', 'tenant_admin', 'doctor', 'receptionist', 'nurse',
            'pharmacist', 'accountant', 'billing_officer', 'super_admin', 'system_admin'
        })


@api_view(['POST'])
@permission_classes([IsPatientBillingStaff])
@transaction.atomic
def record_patient_payment(request):
    if getattr(request.user, 'is_patient', False):
        patient_id = getattr(request.user, 'patient_id', None) or getattr(request.user, 'id', None)
        patient = Patient.objects.select_related('tenant').filter(id=patient_id).first()
        tenant = patient.tenant if patient else None
    else:
        user_tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        tenant = (
            user_tenant
            or getattr(request, 'tenant', None)
            or getattr(connection, 'tenant', None)
        )
    invoice_id = request.data.get('invoice')
    if not tenant or not invoice_id:
        return Response({'detail': 'Tenant and invoice context are required.'}, status=status.HTTP_400_BAD_REQUEST)

    invoice = Invoice.objects.filter(id=invoice_id, tenant=tenant).first()
    if getattr(request.user, 'is_patient', False):
        patient_id = getattr(request.user, 'patient_id', None) or getattr(request.user, 'id', None)
        invoice = invoice if invoice and invoice.patient_id == patient_id else None
    if not invoice:
        return Response({'invoice': ['Invoice not found.']}, status=status.HTTP_404_NOT_FOUND)
    try:
        amount = Decimal(str(request.data.get('amount')))
    except (TypeError, ValueError, ArithmeticError):
        return Response({'amount': ['Enter a valid payment amount.']}, status=status.HTTP_400_BAD_REQUEST)
    if amount <= 0:
        return Response({'amount': ['Payment must be greater than zero.']}, status=status.HTTP_400_BAD_REQUEST)
    if amount > invoice.balance_due:
        return Response({'amount': ['Payment cannot exceed the outstanding balance.']}, status=status.HTTP_400_BAD_REQUEST)

    payment = Payment.objects.create(
        tenant=tenant,
        invoice=invoice,
        patient=invoice.patient,
        amount=amount,
        payment_method=request.data.get('payment_method', 'cash'),
        transaction_reference=str(request.data.get('transaction_reference', '')).strip(),
        received_by=str(request.data.get('received_by', '')).strip() or str(request.user),
        notes=str(request.data.get('notes', '')).strip(),
        status='completed',
    )
    invoice.amount_paid = invoice.payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    invoice.balance_due = invoice.total_amount - invoice.amount_paid
    invoice.status = 'paid' if invoice.balance_due <= 0 else 'partially_paid'
    invoice.save(update_fields=['amount_paid', 'balance_due', 'status', 'updated_at'])
    return Response(InvoiceSerializer(invoice, context={'request': request}).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsClinicalStaff])
@transaction.atomic
def add_patient_charge(request):
    tenant = getattr(request, 'tenant', None) or getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
    if not tenant:
        return Response({'detail': 'Tenant context required.'}, status=status.HTTP_403_FORBIDDEN)

    patient_id = request.data.get('patient')
    if not patient_id:
        return Response({'patient': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

    patient = Patient.objects.filter(id=patient_id, tenant=tenant).first()
    if not patient:
        return Response({'patient': ['Patient not found.']}, status=status.HTTP_404_NOT_FOUND)

    item_type = request.data.get('item_type', 'service')
    description = str(request.data.get('description', '')).strip()
    source_id = str(request.data.get('source_id', '')).strip()
    try:
        quantity = int(request.data.get('quantity', 1))
        unit_price = Decimal(str(request.data.get('unit_price', 0)))
    except (TypeError, ValueError, ArithmeticError):
        return Response({'detail': 'Quantity and unit_price must be valid numbers.'}, status=status.HTTP_400_BAD_REQUEST)
    if not description or quantity <= 0 or unit_price < 0:
        return Response({'detail': 'Description, positive quantity, and non-negative unit_price are required.'}, status=status.HTTP_400_BAD_REQUEST)

    visit_id = request.data.get('visit') or None
    invoice = Invoice.objects.filter(tenant=tenant, patient=patient, visit_id=visit_id, status__in=['draft', 'issued', 'partially_paid']).order_by('-invoice_date').first()
    if not invoice:
        invoice = Invoice(tenant=tenant, patient=patient, visit_id=visit_id, due_date=timezone.now())
        invoice.save()

    if source_id and invoice.items.filter(service_id=source_id).exists():
        return Response(InvoiceSerializer(invoice, context={'request': request}).data)

    line_total = unit_price * quantity
    InvoiceItem.objects.create(
        invoice=invoice,
        item_type=item_type,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        service_id=source_id,
    )
    invoice.subtotal = invoice.items.aggregate(total=Sum('line_total'))['total'] or 0
    invoice.total_amount = invoice.subtotal + invoice.tax_amount - invoice.discount_amount
    invoice.balance_due = invoice.total_amount - invoice.amount_paid
    invoice.patient_amount = invoice.balance_due
    invoice.status = 'issued'
    invoice.save(update_fields=['subtotal', 'total_amount', 'balance_due', 'patient_amount', 'status', 'updated_at'])
    return Response(InvoiceSerializer(invoice, context={'request': request}).data, status=status.HTTP_201_CREATED)


def _plan_amount(plan, billing_period):
    amounts = {
        'monthly': plan.price_monthly,
        'quarterly': plan.price_quarterly,
        'yearly': plan.price_yearly,
    }
    if billing_period not in amounts:
        raise ValueError('billing_period must be monthly, quarterly, or yearly')
    if SUBSCRIPTION_PERIOD_MONTHS[billing_period] > 12:
        raise ValueError('Subscription periods cannot exceed 12 months.')
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
    tenant.include_email_service = payment.include_email_service
    tenant.include_sms_service = payment.include_sms_service
    tenant.email_service_cost = payment.email_service_cost
    tenant.sms_service_cost = payment.sms_service_cost
    tenant.save(update_fields=[
        'subscription_plan', 'subscription_status', 'subscription_start_date',
        'subscription_end_date', 'monthly_fee', 'payment_method',
        'include_email_service', 'include_sms_service', 'email_service_cost', 'sms_service_cost', 'updated_at',
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

        current_plan = tenant.subscription_plan
        monthly_total = Decimal('0')
        if current_plan:
            monthly_total = Decimal(str(current_plan.price_monthly))
            if tenant.include_email_service:
                monthly_total += Decimal(str(current_plan.email_service_cost_monthly))
            if tenant.include_sms_service:
                monthly_total += Decimal(str(current_plan.sms_service_cost_monthly))

        return Response({
            'tenant_id': str(tenant.public_id),
            'tenant_name': tenant.name,
            'subscription_status': tenant.subscription_status,
            'subscription_plan': tenant.subscription_plan_id,
            'subscription_plan_name': current_plan.name if current_plan else None,
            'subscription_start_date': tenant.subscription_start_date,
            'subscription_end_date': tenant.subscription_end_date,
            'days_remaining': tenant.days_remaining,
            'billing_email': tenant.billing_email,
            'include_email_service': tenant.include_email_service,
            'include_sms_service': tenant.include_sms_service,
            'email_service_cost': str(tenant.email_service_cost),
            'sms_service_cost': str(tenant.sms_service_cost),
            'monthly_fee': str(tenant.monthly_fee or monthly_total),
            'current_monthly_total': str(monthly_total),
            'available_plans': [
                {
                    'id': plan.id,
                    'name': plan.name,
                    'code': plan.code,
                    'description': plan.description,
                    'currency': plan.currency,
                    'price_monthly': str(plan.price_monthly),
                    'price_quarterly': str(plan.price_quarterly),
                    'price_yearly': str(plan.price_yearly),
                    'max_users': plan.max_users,
                    'max_patients': plan.max_patients,
                    'max_storage_gb': plan.max_storage_gb,
                    'email_service_cost_monthly': str(plan.email_service_cost_monthly),
                    'sms_service_cost_monthly': str(plan.sms_service_cost_monthly),
                    'is_active': plan.is_active,
                    'service_providers': plan.service_providers,
                }
                for plan in SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price_monthly')
            ],
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
        
        # Service selections
        include_email_service = request.data.get('email_service', False)
        include_sms_service = request.data.get('sms_service', False)
        
        try:
            amount = _plan_amount(plan, billing_period)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate service costs
        email_service_cost = Decimal(0)
        sms_service_cost = Decimal(0)
        
        if include_email_service:
            months_multiplier = SUBSCRIPTION_PERIOD_MONTHS[billing_period]
            email_service_cost = plan.email_service_cost_monthly * months_multiplier
            amount += email_service_cost
            
        if include_sms_service:
            months_multiplier = SUBSCRIPTION_PERIOD_MONTHS[billing_period]
            sms_service_cost = plan.sms_service_cost_monthly * months_multiplier
            amount += sms_service_cost
        
        if amount <= 0:
            return Response({'error': 'This plan has no payable price'}, status=status.HTTP_400_BAD_REQUEST)
        if not payment_setting_configured('paystack_secret_key'):
            return Response({'error': 'Payment provider is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        reference = f"HMS-{tenant.public_id.hex[:12]}-{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
        payment = SubscriptionPayment.objects.create(
            tenant=tenant, plan=plan, reference=reference, amount=amount,
            currency=plan.currency, billing_period=billing_period,
            include_email_service=include_email_service,
            include_sms_service=include_sms_service,
            email_service_cost=email_service_cost,
            sms_service_cost=sms_service_cost,
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
        qs = super().get_queryset().select_related('patient', 'visit').prefetch_related('items', 'payments', 'insurance_claims')
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
        total_pending = Invoice.objects.filter(tenant=tenant, status__in=['issued', 'partially_paid', 'overdue']).aggregate(
            total=Sum('balance_due')
        )['total'] or 0
        
        return Response({
            'total_invoices': total_invoices,
            'total_revenue': float(total_paid),
            'total_invoiced': float(total_revenue),
            'total_paid': float(total_paid),
            'total_pending': float(total_pending),
            'invoiced_total': float(total_revenue),
            'collected_total': float(total_paid),
            'receivables': float(total_pending),
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
        invoiced_total = float(invoices.aggregate(total=Sum('total_amount'))['total'] or 0)
        total_paid = float(invoices.aggregate(total=Sum('amount_paid'))['total'] or 0)
        total_revenue = total_paid
        total_pending = float(invoices.filter(status__in=['issued', 'partially_paid', 'overdue']).aggregate(
            total=Sum('balance_due')
        )['total'] or 0)

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

        # Costs are limited to amounts recorded in the system. Do not estimate
        # salaries, overhead, or drug cost when the source records are absent.
        drug_costs = SaleItem.objects.filter(
            sale__in=sales
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('quantity') * F('drug__unit_price'),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )['total'] or 0

        equipment_maintenance = 0
        try:
            from equipment.models import MaintenanceRecord
            equipment_maintenance = MaintenanceRecord.objects.filter(
                tenant=tenant, date__gte=start_date
            ).aggregate(total=Sum('cost'))['total'] or 0
        except ModuleNotFoundError:
            pass
        equipment_costs = float(equipment_maintenance)

        cost_breakdown = {
            'drugs': float(drug_costs),
            'equipment_maintenance': float(equipment_costs),
        }
        total_costs = sum(cost_breakdown.values())

        # Pharmacy inventory and sales health indicators.
        from pharmacy.models import Drug
        inventory = Drug.objects.filter(tenant=tenant, status='active')
        inventory_summary = inventory.aggregate(
            drug_count=Count('id'),
            units_in_stock=Sum('stock_quantity'),
            stock_value=Sum(
                ExpressionWrapper(
                    F('stock_quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
        low_stock_count = inventory.filter(stock_quantity__lte=F('reorder_level')).count()
        units_sold = SaleItem.objects.filter(sale__in=sales).aggregate(total=Sum('quantity'))['total'] or 0
        sales_by_day = sales.annotate(day=TruncDate('sold_at')).values('day').annotate(
            amount=Sum('total_amount'), count=Count('id')
        ).order_by('day')
        sales_trend = [
            {'date': item['day'].isoformat(), 'amount': float(item['amount'] or 0), 'count': item['count']}
            for item in sales_by_day
        ]

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

        kpis = {
            'financial': {
                'costPerPatient': total_costs / max(invoices.count(), 1),
                'operatingMargin': ((total_revenue - total_costs) / total_revenue * 100) if total_revenue > 0 else 0,
            },
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
            'pharmacy': {
                'drugCount': inventory_summary['drug_count'] or 0,
                'unitsInStock': inventory_summary['units_in_stock'] or 0,
                'stockValue': float(inventory_summary['stock_value'] or 0),
                'lowStockCount': low_stock_count,
                'unitsSold': units_sold,
                'salesRevenue': float(sales.aggregate(total=Sum('total_amount'))['total'] or 0),
                'salesTrend': sales_trend,
            },
            'invoices': {
                'total': invoices.count(),
                'paid': invoices.filter(status='paid').count(),
                'pending': invoices.filter(status__in=['issued', 'partially_paid', 'overdue']).count(),
                'invoiced_total': invoiced_total,
                'collected_total': float(total_paid),
                'receivables': float(total_pending),
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
