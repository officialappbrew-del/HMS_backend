from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import BaseModel, EncryptedField
from tenants.models import Tenant


class Account(BaseModel):
    class AccountType(models.TextChoices):
        ASSET = 'asset', 'Asset'
        LIABILITY = 'liability', 'Liability'
        EQUITY = 'equity', 'Equity'
        REVENUE = 'revenue', 'Revenue'
        EXPENSE = 'expense', 'Expense'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')

    class Meta:
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['tenant', 'code'], name='unique_account_code_per_tenant')]


class JournalEntry(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        APPROVED = 'approved', 'Approved'
        POSTED = 'posted', 'Posted'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='journal_entries')
    entry_number = models.CharField(max_length=40)
    entry_date = models.DateField()
    particulars = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_journal_entries')

    class Meta:
        ordering = ['-entry_date', '-created_at']
        constraints = [models.UniqueConstraint(fields=['tenant', 'entry_number'], name='unique_journal_number_per_tenant')]


class JournalLine(BaseModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    reference = models.CharField(max_length=100, blank=True)


class Vendor(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='accounting_vendors')
    vendor_number = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    vendor_type = models.CharField(max_length=50, default='other')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=30, blank=True)
    pan_number = EncryptedField(blank=True, default='')
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = EncryptedField(blank=True, default='')
    ifsc_code = models.CharField(max_length=20, blank=True)
    credit_period_days = models.PositiveIntegerField(default=30)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['tenant', 'vendor_number'], name='unique_vendor_number_per_tenant')]


class PurchaseOrder(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        APPROVED = 'approved', 'Approved'
        ORDERED = 'ordered', 'Ordered'
        RECEIVED = 'received', 'Received'
        INVOICED = 'invoiced', 'Invoiced'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='purchase_orders')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='purchase_orders')
    po_number = models.CharField(max_length=40)
    po_date = models.DateField()
    expected_delivery = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-po_date']
        constraints = [models.UniqueConstraint(fields=['tenant', 'po_number'], name='unique_po_number_per_tenant')]


class PurchaseOrderLine(BaseModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    item_name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, default='other')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)


class VendorPayment(BaseModel):
    class Method(models.TextChoices):
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        CHEQUE = 'cheque', 'Cheque'
        CASH = 'cash', 'Cash'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        PAID = 'paid', 'Paid'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vendor_payments')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='payments')
    payment_number = models.CharField(max_length=40)
    invoice_numbers = models.JSONField(default=list)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    net_payable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=Method.choices, default=Method.BANK_TRANSFER)
    payment_date = models.DateField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['tenant', 'payment_number'], name='unique_vendor_payment_per_tenant')]


class Asset(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        TRANSFERRED = 'transferred', 'Transferred'
        DISPOSED = 'disposed', 'Disposed'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='accounting_assets')
    asset_number = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    department = models.CharField(max_length=200, blank=True)
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    useful_life_years = models.PositiveIntegerField(default=5)
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    serial_number = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['tenant', 'asset_number'], name='unique_asset_number_per_tenant')]

    @property
    def annual_depreciation(self):
        if not self.useful_life_years:
            return 0
        return (self.purchase_cost - self.salvage_value) / self.useful_life_years


class TaxConfiguration(BaseModel):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='accounting_tax_configuration')
    hospital_gstin = models.CharField(max_length=30, blank=True)
    gst_rates = models.JSONField(default=dict)
    tds_rates = models.JSONField(default=dict)
    gst_period = models.CharField(max_length=20, default='monthly')
