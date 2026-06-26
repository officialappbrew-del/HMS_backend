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
    strength = models.CharField(max_length=100, blank=True)
    therapeutic_class = models.CharField(max_length=100, blank=True)

    # Inventory
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=10)
    reorder_quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_of_measure = models.CharField(max_length=50, blank=True)
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    storage_conditions = models.CharField(max_length=200, blank=True)
    last_restocked = models.DateField(null=True, blank=True)

    # Nigerian Specific
    nafdac_number = models.CharField(max_length=50, blank=True)
    pcn_approval_number = models.CharField(max_length=50, blank=True)
    neml_category = models.CharField(max_length=50, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    country_of_origin = models.CharField(max_length=100, default='Nigeria')
    is_controlled = models.BooleanField(default=False)
    narcotic = models.BooleanField(default=False)
    schedule = models.CharField(max_length=50, blank=True)

    # NHIS
    nhis_covered = models.BooleanField(default=False)
    nhis_code = models.CharField(max_length=50, blank=True)
    nhis_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Clinical
    side_effects = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    interactions = models.TextField(blank=True)
    dosage_instructions = models.TextField(blank=True)
    prescription_required = models.BooleanField(default=False)

    # Misc
    barcode = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='active', choices=[
        ('active', 'Active'),
        ('archived', 'Archived'),
        ('discontinued', 'Discontinued')
    ])

    def __str__(self):
        return f"{self.name} ({self.strength})"

    class Meta:
        verbose_name = _('Drug')
        verbose_name_plural = _('Drugs')
        ordering = ['name']


class Supplier(BaseModel):
    """Drug suppliers/vendors."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    rating = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Supplier')
        verbose_name_plural = _('Suppliers')
        ordering = ['name']


class Sale(BaseModel):
    """Pharmacy sales/POS transactions."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='sales')
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name='pharmacy_sales')
    sold_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, related_name='pharmacy_sales')

    # Financials
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=[
        ('cash', 'Cash'),
        ('nhis', 'NHIS'),
        ('hmo', 'HMO'),
        ('card', 'Card'),
        ('transfer', 'Transfer'),
    ], default='cash')
    payment_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ], default='pending')
    status = models.CharField(max_length=20, choices=[
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ], default='completed')

    # Additional
    notes = models.TextField(blank=True)
    sold_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale #{self.id} - {self.total_amount}"

    class Meta:
        verbose_name = _('Sale')
        verbose_name_plural = _('Sales')
        ordering = ['-sold_at']


class SaleItem(BaseModel):
    """Individual items within a sale."""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name='sale_items')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.drug.name} x {self.quantity}"

    class Meta:
        verbose_name = _('Sale Item')
        verbose_name_plural = _('Sale Items')
        ordering = ['sale', 'id']


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

    def save(self, *args, **kwargs):
        if self.unit_price is not None and self.quantity is not None:
            self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Dispense #{self.id} - {self.drug.name} to {self.patient.get_full_name()}"

    class Meta:
        verbose_name = _('Dispense')
        verbose_name_plural = _('Dispenses')
        ordering = ['-dispensed_date']
