from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant


class Budget(BaseModel):
    """Department/category budget records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='budgets')
    department = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    year = models.PositiveIntegerField()
    period = models.CharField(max_length=20, choices=[
        ('annual', 'Annual'),
        ('quarterly', 'Quarterly'),
        ('monthly', 'Monthly')
    ], default='annual')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    utilized = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('pending', 'Pending Approval'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('completed', 'Completed')
    ], default='draft')
    approval_required = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('Budget')
        verbose_name_plural = _('Budgets')
        ordering = ['-year', 'department']
        indexes = [
            models.Index(fields=['tenant', 'department', 'year']),
            models.Index(fields=['tenant', 'status', '-year']),
        ]
    
    def __str__(self):
        return f"{self.department} - {self.category} ({self.year})"
    
    @property
    def variance(self):
        if self.amount > 0:
            return round(((float(self.utilized) - float(self.amount)) / float(self.amount)) * 100, 1)
        return 0


class Forecast(BaseModel):
    """Financial forecasts."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='forecasts')
    category = models.CharField(max_length=100)
    period = models.CharField(max_length=20, choices=[
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual')
    ], default='quarterly')
    year = models.PositiveIntegerField()
    predicted_amount = models.DecimalField(max_digits=12, decimal_places=2)
    confidence_level = models.PositiveIntegerField(default=0)
    assumptions = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    accuracy = models.PositiveIntegerField(default=0)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        verbose_name = _('Forecast')
        verbose_name_plural = _('Forecasts')
        ordering = ['-year', 'category']
        indexes = [
            models.Index(fields=['tenant', 'category', 'year']),
        ]
    
    def __str__(self):
        return f"{self.category} Forecast {self.year}"


class Grant(BaseModel):
    """Grant and donor funding records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='grants')
    name = models.CharField(max_length=200)
    donor = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    purpose = models.TextField()
    conditions = models.TextField(blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    reporting_frequency = models.CharField(max_length=20, choices=[
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-Annual'),
        ('annual', 'Annual')
    ], default='quarterly')
    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated')
    ], default='active')
    utilized = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_report_date = models.DateField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('Grant')
        verbose_name_plural = _('Grants')
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['tenant', 'status', '-start_date']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.donor}"


class BudgetVariance(BaseModel):
    """Budget variance tracking."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='budget_variances')
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='variances')
    period = models.CharField(max_length=20)
    year = models.PositiveIntegerField()
    planned_amount = models.DecimalField(max_digits=12, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2)
    variance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    variance_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)
    alert_triggered = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = _('Budget Variance')
        verbose_name_plural = _('Budget Variances')
        ordering = ['-year', 'period']
        indexes = [
            models.Index(fields=['tenant', 'budget', '-year']),
        ]
    
    def __str__(self):
        return f"{self.budget.department} - {self.period} {self.year}"


class BudgetReport(BaseModel):
    """Generated budget reports."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='budget_reports')
    report_type = models.CharField(max_length=50, choices=[
        ('annual_budget', 'Annual Budget Report'),
        ('variance_analysis', 'Variance Analysis Report'),
        ('forecast_accuracy', 'Forecast Accuracy Report'),
        ('grant_utilization', 'Grant Utilization Report'),
        ('departmental', 'Departmental Report'),
        ('custom', 'Custom Report')
    ])
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    generated_by = models.CharField(max_length=200, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    summary = models.TextField(blank=True)
    
    class Meta:
        verbose_name = _('Budget Report')
        verbose_name_plural = _('Budget Reports')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.period_start} to {self.period_end})"
