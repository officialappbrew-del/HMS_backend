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
        ('paid', 'PaID')
    ], default='not_submitted')
    
    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-invoice_date']