from django.contrib import admin
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim, BillingAuditLog


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'patient', 'total_amount', 'amount_paid', 'balance_due', 'status', 'invoice_date']
    list_filter = ['tenant', 'status', 'invoice_date', 'nhis_status', 'insurance_covered']
    search_fields = ['invoice_number', 'patient__first_name', 'patient__last_name', 'notes']
    readonly_fields = ['invoice_number', 'invoice_date', 'created_at', 'updated_at', 'is_active']
    date_hierarchy = 'invoice_date'


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'item_type', 'description', 'quantity', 'unit_price', 'line_total']
    list_filter = ['item_type', 'invoice__status']
    search_fields = ['description', 'invoice__invoice_number']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'invoice', 'patient', 'amount', 'payment_method', 'status', 'payment_date']
    list_filter = ['tenant', 'payment_method', 'status', 'payment_date']
    search_fields = ['payment_number', 'invoice__invoice_number', 'transaction_reference', 'notes']
    readonly_fields = ['payment_number', 'payment_date', 'created_at', 'updated_at', 'is_active']


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ['claim_number', 'patient', 'insurance_provider', 'claimed_amount', 'approved_amount', 'status', 'claim_date']
    list_filter = ['tenant', 'insurance_provider', 'status', 'nhis_status', 'claim_date']
    search_fields = ['claim_number', 'insurance_provider', 'policy_number', 'nhis_claim_number', 'notes']
    readonly_fields = ['claim_number', 'claim_date', 'created_at', 'updated_at', 'is_active']


@admin.register(BillingAuditLog)
class BillingAuditLogAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'action', 'user', 'created_at']
    list_filter = ['tenant', 'action', 'created_at']
    search_fields = ['description', 'user', 'invoice__invoice_number']
    readonly_fields = ['created_at', 'updated_at', 'is_active']
