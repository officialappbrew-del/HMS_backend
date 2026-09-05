from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator

from core.models import BaseModel
from tenants.models import Tenant, TenantUser


class AttendanceRecord(BaseModel):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        HALF_DAY = 'half_day', 'Half-Day'
        LEAVE = 'leave', 'Leave'
        HOLIDAY = 'holiday', 'Holiday'
        WEEKLY_OFF = 'weekly_off', 'Weekly-Off'

    class Source(models.TextChoices):
        BIOMETRIC = 'biometric', 'Biometric'
        MANUAL = 'manual', 'Manual'
        FACE_ID = 'face_id', 'Face ID'
        MOBILE = 'mobile', 'Mobile'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_attendance')
    employee = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    check_in_source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    check_out_source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    late_minutes = models.PositiveIntegerField(default=0)
    early_minutes = models.PositiveIntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    shift_type = models.CharField(max_length=20, default='general')
    remarks = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date', 'employee__first_name']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'employee', 'date'], name='unique_hr_attendance_day'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'status', 'date']),
        ]


class LeaveApplication(BaseModel):
    class LeaveType(models.TextChoices):
        CASUAL = 'casual', 'Casual'
        SICK = 'sick', 'Sick'
        ANNUAL = 'annual', 'Annual'
        MATERNITY = 'maternity', 'Maternity'
        PATERNITY = 'paternity', 'Paternity'
        STUDY = 'study', 'Study'
        COMPENSATORY = 'compensatory', 'Compensatory'
        UNPAID = 'unpaid', 'Unpaid'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_leave_applications')
    employee = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name='leave_applications')
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.PositiveIntegerField()
    reason = models.TextField()
    document = models.FileField(upload_to='hr/leave-documents/', null=True, blank=True)
    alternate_contact = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_hr_leaves')
    review_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status', 'start_date']),
            models.Index(fields=['tenant', 'employee', 'start_date']),
        ]


class SalaryStructure(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_salary_structures')
    employee = models.OneToOneField(TenantUser, on_delete=models.CASCADE, related_name='salary_structure')
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    housing_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    transport_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    medical_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    other_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    pf_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=12)
    esi_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.75)
    professional_tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    active_from = models.DateField()


class PayrollRun(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        READY = 'ready', 'Ready'
        SENT_TO_ACCOUNTS = 'sent_to_accounts', 'Sent to Accounts'
        PAID = 'paid', 'Paid'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_payroll_runs')
    month = models.DateField(help_text='Use the first day of the payroll month.')
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'month'], name='unique_payroll_month_per_tenant')]
        ordering = ['-month']


class PayrollLine(BaseModel):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='lines')
    employee = models.ForeignKey(TenantUser, on_delete=models.PROTECT, related_name='payroll_lines')
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2)
    allowances = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
