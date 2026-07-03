from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient, PatientVisit


class Invoice(BaseModel):
    """Patient invoices/bills."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invoices')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='invoices')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='invoices',
                             null=True, blank=True)
    
    # Invoice Information
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Payment Status
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled')
    ], default='draft')
    
    # Insurance
    insurance_covered = models.BooleanField(default=False)
    insurance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    patient_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # NHIS Specific
    nhis_claim_number = models.CharField(max_length=50, blank=True)
    nhis_status = models.CharField(max_length=20, choices=[
        ('not_submitted', 'Not Submitted'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid')
    ], default='not_submitted')
    
    # Meta
    notes = models.TextField(blank=True)
    created_by = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-invoice_date']
        indexes = [
            models.Index(fields=['tenant', 'patient', '-invoice_date']),
            models.Index(fields=['tenant', 'status', '-invoice_date']),
        ]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            if self.id:
                self.invoice_number = f"INV-{self.id}"
            else:
                super().save(*args, **kwargs)
                self.invoice_number = f"INV-{self.id}"
                kwargs['update_fields'] = ['invoice_number']
        super().save(*args, **kwargs)


class InvoiceItem(BaseModel):
    """Line items on an invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=50, choices=[
        ('consultation', 'Consultation'),
        ('drug', 'Drug/Medication'),
        ('service', 'Medical Service'),
        ('test', 'Lab Test/Investigation'),
        ('procedure', 'Procedure'),
        ('admission', 'Admission/Bed'),
        ('other', 'Other')
    ])
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Optional references
    drug_id = models.CharField(max_length=50, blank=True)
    service_id = models.CharField(max_length=50, blank=True)
    
    class Meta:
        verbose_name = _('Invoice Item')
        verbose_name_plural = _('Invoice Items')
        ordering = ['id']
    
    def __str__(self):
        return f"{self.description} - {self.line_total}"


class Payment(BaseModel):
    """Payments made against invoices."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='payments')
    
    # Payment Information
    payment_number = models.CharField(max_length=50, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=[
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Bank Transfer'),
        ('pos', 'POS'),
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
        ('insurance', 'Insurance'),
        ('other', 'Other')
    ])
    
    # Transaction details
    transaction_reference = models.CharField(max_length=100, blank=True)
    received_by = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded')
    ], default='completed')
    
    class Meta:
        verbose_name = _('Payment')
        verbose_name_plural = _('Payments')
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['tenant', 'invoice', '-payment_date']),
            models.Index(fields=['tenant', 'patient', '-payment_date']),
        ]
    
    def __str__(self):
        return f"Payment #{self.payment_number} - {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.payment_number:
            if self.id:
                self.payment_number = f"PAY-{self.id}"
            else:
                super().save(*args, **kwargs)
                self.payment_number = f"PAY-{self.id}"
                kwargs['update_fields'] = ['payment_number']
        super().save(*args, **kwargs)


class InsuranceClaim(BaseModel):
    """Insurance/NHIS claims."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='insurance_claims')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='insurance_claims')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='insurance_claims')
    
    # Claim Information
    claim_number = models.CharField(max_length=50, unique=True)
    claim_date = models.DateTimeField(auto_now_add=True)
    insurance_provider = models.CharField(max_length=200)
    policy_number = models.CharField(max_length=100, blank=True)
    
    # Amounts
    claimed_amount = models.DecimalField(max_digits=10, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rejected_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Claim Status
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], default='draft')
    
    # NHIS Specific
    nhis_claim_number = models.CharField(max_length=50, blank=True)
    nhis_status = models.CharField(max_length=20, choices=[
        ('not_submitted', 'Not Submitted'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid')
    ], default='not_submitted')
    
    # Dates
    submitted_date = models.DateTimeField(null=True, blank=True)
    processed_date = models.DateTimeField(null=True, blank=True)
    paid_date = models.DateTimeField(null=True, blank=True)
    
    # Notes and documentation
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    supporting_documents = models.JSONField(default=list, blank=True)
    
    class Meta:
        verbose_name = _('Insurance Claim')
        verbose_name_plural = _('Insurance Claims')
        ordering = ['-claim_date']
        indexes = [
            models.Index(fields=['tenant', 'patient', '-claim_date']),
            models.Index(fields=['tenant', 'status', '-claim_date']),
        ]
    
    def __str__(self):
        return f"Claim #{self.claim_number} - {self.insurance_provider}"
    
    def save(self, *args, **kwargs):
        if not self.claim_number:
            if self.id:
                self.claim_number = f"CLM-{self.id}"
            else:
                super().save(*args, **kwargs)
                self.claim_number = f"CLM-{self.id}"
                kwargs['update_fields'] = ['claim_number']
        super().save(*args, **kwargs)


class BillingAuditLog(BaseModel):
    """Audit trail for billing operations."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='billing_audit_logs')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    action = models.CharField(max_length=50, choices=[
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('claim_submitted', 'Claim Submitted'),
        ('claim_approved', 'Claim Approved'),
        ('claim_rejected', 'Claim Rejected')
    ])
    description = models.TextField()
    user = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('Billing Audit Log')
        verbose_name_plural = _('Billing Audit Logs')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.action} - {self.created_at}"
