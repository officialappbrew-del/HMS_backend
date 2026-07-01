from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient


class WardRound(BaseModel):
    """Ward round records for daily rounds, teaching rounds, etc."""
    class RoundType(models.TextChoices):
        DAILY = 'Daily Ward Round', _('Daily Ward Round')
        TEACHING = 'Teaching Round', _('Teaching Round')
        GRAND = 'Grand Round', _('Grand Round')
        DISCHARGE = 'Discharge Round', _('Discharge Round')

    class RoundStatus(models.TextChoices):
        SCHEDULED = 'Scheduled', _('Scheduled')
        IN_PROGRESS = 'In Progress', _('In Progress')
        COMPLETED = 'Completed', _('Completed')
        CANCELLED = 'Cancelled', _('Cancelled')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ward_rounds')
    ward_id = models.CharField(max_length=50)
    ward_name = models.CharField(max_length=200)
    round_type = models.CharField(max_length=30, choices=RoundType.choices, default=RoundType.DAILY)
    status = models.CharField(max_length=20, choices=RoundStatus.choices, default=RoundStatus.SCHEDULED)
    date = models.DateTimeField()
    time = models.TimeField()
    consultant = models.CharField(max_length=200)
    consultant_specialty = models.CharField(max_length=200, blank=True)
    team_members = models.JSONField(default=list, blank=True)
    patients_list = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    expected_duration = models.IntegerField(default=120, help_text=_('Duration in minutes'))
    actual_duration = models.IntegerField(null=True, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    completed_time = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    round_documentation = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _('Ward Round')
        verbose_name_plural = _('Ward Rounds')
        ordering = ['-date', '-time']
        indexes = [
            models.Index(fields=['tenant', 'status', '-date']),
            models.Index(fields=['ward_id', 'date']),
        ]

    def __str__(self):
        return f"{self.ward_name} - {self.round_type} ({self.get_status_display()})"


class HandoverNote(BaseModel):
    """Handover notes between shifts."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='handover_notes')
    ward_id = models.CharField(max_length=50)
    ward_name = models.CharField(max_length=200)
    date = models.DateTimeField()
    shift_from = models.CharField(max_length=50)
    shift_to = models.CharField(max_length=50)
    handover_officer = models.CharField(max_length=200)
    receiving_officer = models.CharField(max_length=200)
    critically_severe = models.JSONField(default=list, blank=True)
    recent_admissions = models.JSONField(default=list, blank=True)
    pending_procedures = models.JSONField(default=list, blank=True)
    pending_discharges = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Handover Note')
        verbose_name_plural = _('Handover Notes')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['tenant', 'ward_id', '-date']),
        ]

    def __str__(self):
        return f"{self.ward_name} - {self.shift_from} to {self.shift_to}"


class GrandRound(BaseModel):
    """Grand rounds for teaching and case discussions."""
    class RoundStatus(models.TextChoices):
        SCHEDULED = 'Scheduled', _('Scheduled')
        IN_PROGRESS = 'In Progress', _('In Progress')
        COMPLETED = 'Completed', _('Completed')
        CANCELLED = 'Cancelled', _('Cancelled')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='grand_rounds')
    date = models.DateTimeField()
    time = models.TimeField()
    status = models.CharField(max_length=20, choices=RoundStatus.choices, default=RoundStatus.SCHEDULED)
    topic = models.CharField(max_length=300)
    presenter = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    target_audience = models.TextField(blank=True)
    case_studies = models.JSONField(default=list, blank=True)
    expected_attendees = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Grand Round')
        verbose_name_plural = _('Grand Rounds')
        ordering = ['-date', '-time']
        indexes = [
            models.Index(fields=['tenant', 'status', '-date']),
        ]

    def __str__(self):
        return f"{self.topic} - {self.get_status_display()}"


class Ward(BaseModel):
    """Ward and bed grouping for inpatient allocation."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='wards')
    ward_id = models.CharField(max_length=50)
    ward_name = models.CharField(max_length=200)
    ward_type = models.CharField(max_length=100, default='General Ward')
    floor = models.CharField(max_length=50, blank=True)
    supervisor = models.CharField(max_length=200, blank=True)
    staff_count = models.PositiveIntegerField(default=0)
    total_beds = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Ward')
        verbose_name_plural = _('Wards')
        ordering = ['ward_name']
        unique_together = [['tenant', 'ward_id']]
        indexes = [
            models.Index(fields=['tenant', 'ward_id']),
            models.Index(fields=['ward_name']),
        ]

    def __str__(self):
        return f"{self.ward_name} ({self.ward_id})"


class Bed(BaseModel):
    """Individual bed within a ward."""
    class Status(models.TextChoices):
        AVAILABLE = 'Available', _('Available')
        OCCUPIED = 'Occupied', _('Occupied')
        RESERVED = 'Reserved', _('Reserved')
        UNDER_CLEANING = 'Under Cleaning', _('Under Cleaning')
        MAINTENANCE = 'Maintenance', _('Maintenance')

    class CleaningStatus(models.TextChoices):
        CLEAN = 'Clean', _('Clean')
        UNDER_CLEANING = 'Under Cleaning', _('Under Cleaning')
        MAINTENANCE = 'Maintenance', _('Maintenance')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='beds')
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='beds')
    bed_id = models.CharField(max_length=50)
    bed_number = models.PositiveIntegerField()
    bed_type = models.CharField(max_length=100, default='Standard')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.AVAILABLE)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name='beds')
    is_private = models.BooleanField(default=False)
    cleaning_status = models.CharField(max_length=30, choices=CleaningStatus.choices, default=CleaningStatus.CLEAN)
    last_cleaned = models.DateTimeField(null=True, blank=True)
    last_turnover = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Bed')
        verbose_name_plural = _('Beds')
        ordering = ['ward', 'bed_number']
        unique_together = [['ward', 'bed_number'], ['ward', 'bed_id']]
        indexes = [
            models.Index(fields=['tenant', 'ward', 'status']),
            models.Index(fields=['ward', 'bed_number']),
        ]

    def __str__(self):
        return f"{self.ward.ward_name} - Bed {self.bed_number}"
