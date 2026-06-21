from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient, PatientVisit


class LabTest(BaseModel):
    """Laboratory test catalog."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lab_tests')
    
    # Test Information
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=100, choices=[
        ('hematology', 'Hematology'),
        ('biochemistry', 'Biochemistry'),
        ('microbiology', 'Microbiology'),
        ('urinalysis', 'Urinalysis'),
        ('hormonal', 'Hormonal'),
        ('immunology', 'Immunology'),
        ('molecular', 'Molecular'),
        ('other', 'Other')
    ])
    
    # Test Details
    sample_type = models.CharField(max_length=100)  # e.g., Blood, Urine, Stool
    turnaround_time = models.IntegerField(help_text='Turnaround time in hours')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Reference Ranges
    reference_range = models.TextField(blank=True)
    units = models.CharField(max_length=50, blank=True)
    
    # Critical values
    critical_low = models.CharField(max_length=50, blank=True, help_text='Critical low value')
    critical_high = models.CharField(max_length=50, blank=True, help_text='Critical high value')
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        verbose_name = _('Lab Test')
        verbose_name_plural = _('Lab Tests')
        ordering = ['name']


class LabOrder(BaseModel):
    """Laboratory test orders."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lab_orders')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='lab_orders')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='lab_orders',
                             null=True, blank=True)
    
    # Order Information
    order_number = models.CharField(max_length=50, unique=True)
    test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name='orders')
    
    # Clinical Information
    clinical_notes = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('ordered', 'Ordered'),
        ('collected', 'Sample Collected'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], default='ordered')
    
    # Priority
    priority = models.CharField(max_length=20, choices=[
        ('routine', 'Routine'),
        ('priority', 'Priority'),
        ('stat', 'STAT'),
    ], default='routine')
    
    # Staff
    ordered_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                  limit_choices_to={'role': 'doctor'})
    collected_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    limit_choices_to={'role': 'lab_tech'}, related_name='collected_orders')
    performed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    limit_choices_to={'role': 'lab_tech'}, related_name='performed_orders')
    
    # Timing
    ordered_date = models.DateTimeField(auto_now_add=True)
    collected_date = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    # Sample Information
    sample_accession_number = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return f"Lab Order #{self.order_number} - {self.test.name}"
    
    class Meta:
        verbose_name = _('Lab Order')
        verbose_name_plural = _('Lab Orders')
        ordering = ['-ordered_date']


class LabResult(BaseModel):
    """Laboratory test results."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lab_results')
    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name='results')
    
    # Result Values
    value = models.CharField(max_length=200)
    value_numeric = models.DecimalField(max_digits=15, decimal_places=5, null=True, blank=True)
    units = models.CharField(max_length=50, blank=True)
    
    # Reference Range
    reference_range = models.TextField(blank=True)
    reference_low = models.DecimalField(max_digits=15, decimal_places=5, null=True, blank=True)
    reference_high = models.DecimalField(max_digits=15, decimal_places=5, null=True, blank=True)
    
    # Flagging
    is_critical = models.BooleanField(default=False)
    flag = models.CharField(max_length=10, choices=[
        ('L', 'Low'),
        ('H', 'High'),
        ('LL', 'Critical Low'),
        ('HH', 'Critical High'),
        ('A', 'Abnormal'),
        ('', 'Normal'),
    ], default='')
    
    # Status
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    limit_choices_to={'role__in': ['lab_tech', 'lab_manager']},
                                    related_name='verified_results')
    verified_date = models.DateTimeField(null=True, blank=True)
    
    # Notes
    result_notes = models.TextField(blank=True)
    instrument_reading = models.TextField(blank=True, help_text='Raw data from instrument')
    
    def __str__(self):
        return f"Result for {self.order.test.name}: {self.value}"
    
    class Meta:
        verbose_name = _('Lab Result')
        verbose_name_plural = _('Lab Results')
        ordering = ['-created_at']


class NCDCReport(BaseModel):
    """NCDC notifiable disease reports."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ncdc_reports')
    
    # Report Information
    report_type = models.CharField(max_length=100, choices=[
        ('lassa_fever', 'Lassa Fever'),
        ('cholera', 'Cholera'),
        ('yellow_fever', 'Yellow Fever'),
        ('measles', 'Measles'),
        ('meningitis', 'Meningitis'),
        ('covid19', 'COVID-19'),
        ('other', 'Other Notifiable Disease'),
    ])
    
    # Case Information
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    case_count = models.IntegerField(default=1)
    
    # Location
    lga = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('acknowledged', 'Acknowledged'),
        ('investigating', 'Under Investigation'),
        ('closed', 'Closed'),
    ], default='draft')
    
    # NCDC Reference
    ncdc_reference = models.CharField(max_length=50, blank=True)
    submitted_date = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"NCDC Report: {self.get_report_type_display()} - {self.case_count} cases"
    
    class Meta:
        verbose_name = _('NCDC Report')
        verbose_name_plural = _('NCDC Reports')
        ordering = ['-created_at']


class InstrumentMaintenance(BaseModel):
    """Laboratory instrument maintenance records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='instrument_maintenance')
    
    # Instrument Information
    instrument_name = models.CharField(max_length=200)
    instrument_type = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, blank=True)
    
    # Maintenance Details
    maintenance_type = models.CharField(max_length=50, choices=[
        ('routine', 'Routine Maintenance'),
        ('calibration', 'Calibration'),
        ('repair', 'Repair'),
        ('inspection', 'Inspection'),
        ('emergency', 'Emergency Repair'),
    ])
    description = models.TextField()
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='pending')
    
    # Priority
    priority = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium')
    
    # Timing
    scheduled_date = models.DateTimeField()
    completed_date = models.DateTimeField(null=True, blank=True)
    
    # Technician
    performed_by = models.CharField(max_length=200, blank=True)
    vendor_name = models.CharField(max_length=200, blank=True)
    
    # Cost
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    def __str__(self):
        return f"{self.instrument_name} - {self.get_maintenance_type_display()}"
    
    class Meta:
        verbose_name = _('Instrument Maintenance')
        verbose_name_plural = _('Instrument Maintenances')
        ordering = ['-scheduled_date']
