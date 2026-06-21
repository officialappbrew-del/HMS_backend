from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient
from clinical.models import Prescription


class Drug(BaseModel):
    """Drug/medication inventory."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='drugs')
    
    # Drug Information
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    brand_name = models.CharField(max_length=200, blank=True)
    drug_code = models.CharField(max_length=50, unique=True)
    
    # Classification
    category = models.CharField(max_length=100, choices=[
        ('antibiotic', 'Antibiotic'),
        ('analgesic', 'Analgesic'),
        ('antihypertensive', 'Antihypertensive'),
        ('antidiabetic', 'Antidiabetic'),
        ('antimalarial', 'Antimalarial'),
        ('vaccine', 'Vaccine'),
        ('supplement', 'Supplement'),
        ('other', 'Other')
    ])
    form = models.CharField(max_length=50, choices=[
        ('tablet', 'Tablet'),
        ('capsule', 'Capsule'),
        ('syrup', 'Syrup'),
        ('injection', 'Injection'),
        ('ointment', 'Ointment'),
        ('cream', 'Cream'),
        ('drops', 'Drops'),
        ('inhaler', 'Inhaler'),
        ('suppository', 'Suppository')
    ])
    strength = models.CharField(max_length=100, blank=True)  # e.g., 500mg, 10mg/ml
    
    # Inventory
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=10)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Nigerian Specific
    nafdac_number = models.CharField(max_length=50, blank=True)  # NAFDAC registration
    is_controlled = models.BooleanField(default=False)  # Controlled substance
    
    def __str__(self):
        return f"{self.name} ({self.strength})"
    
    class Meta:
        verbose_name = _('Drug')
        verbose_name_plural = _('Drugs')
        ordering = ['name']


class Dispense(BaseModel):
    """Drug dispensing records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='dispenses')
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='dispenses')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dispenses')
    
    # Dispensing Details
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name='dispenses')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Dispenser
    dispensed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                    limit_choices_to={'role': 'pharmacist'})
    dispensed_date = models.DateTimeField(auto_now_add=True)
    
    # Instructions
    instructions = models.TextField(blank=True)
    
    def __str__(self):
        return f"Dispense #{self.id} - {self.drug.name} to {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Dispense')
        verbose_name_plural = _('Dispenses')
        ordering = ['-dispensed_date']