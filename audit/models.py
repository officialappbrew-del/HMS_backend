from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient


class ClinicalAudit(BaseModel):
    """Clinical audit records."""
    class AuditType(models.TextChoices):
        CLINICAL = 'clinical', _('Clinical Audit')
        ADMINISTRATIVE = 'administrative', _('Administrative Audit')
        QUALITY = 'quality', _('Quality Assurance')
        COMPLIANCE = 'compliance', _('Compliance Audit')
        PEER_REVIEW = 'peer_review', _('Peer Review')

    class AuditStatus(models.TextChoices):
        SCHEDULED = 'scheduled', _('Scheduled')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        OVERDUE = 'overdue', _('Overdue')
        CANCELLED = 'cancelled', _('Cancelled')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='clinical_audits')
    title = models.CharField(max_length=300)
    audit_type = models.CharField(max_length=30, choices=AuditType.choices, default=AuditType.CLINICAL)
    status = models.CharField(max_length=20, choices=AuditStatus.choices, default=AuditStatus.SCHEDULED)
    department = models.CharField(max_length=100)
    auditor = models.CharField(max_length=200)
    scheduled_date = models.DateTimeField()
    completion_date = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    findings = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    action_plan = models.JSONField(default=list, blank=True)
    follow_up_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Clinical Audit')
        verbose_name_plural = _('Clinical Audits')
        ordering = ['-scheduled_date']
        indexes = [
            models.Index(fields=['tenant', 'status', '-scheduled_date']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class QualityIndicator(BaseModel):
    """Quality assurance indicators."""
    class Category(models.TextChoices):
        CLINICAL = 'clinical', _('Clinical Quality')
        SAFETY = 'safety', _('Patient Safety')
        EFFICIENCY = 'efficiency', _('Operational Efficiency')
        SATISFACTION = 'satisfaction', _('Patient Satisfaction')
        COMPLIANCE = 'compliance', _('Compliance')

    class Status(models.TextChoices):
        EXCELLENT = 'excellent', _('Excellent')
        GOOD = 'good', _('Good')
        WARNING = 'warning', _('Warning')
        CRITICAL = 'critical', _('Critical')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='quality_indicators')
    name = models.CharField(max_length=300)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.CLINICAL)
    target = models.CharField(max_length=50)
    current = models.CharField(max_length=50)
    unit = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually')
    ], default='monthly')
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GOOD)
    history = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Quality Indicator')
        verbose_name_plural = _('Quality Indicators')
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class PeerReview(BaseModel):
    """Peer review sessions."""
    class ReviewStatus(models.TextChoices):
        SCHEDULED = 'scheduled', _('Scheduled')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='peer_reviews')
    audit = models.ForeignKey(ClinicalAudit, on_delete=models.CASCADE, related_name='peer_reviews')
    title = models.CharField(max_length=300)
    scheduled_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.SCHEDULED)
    reviewers = models.JSONField(default=list)
    cases_count = models.IntegerField(default=0)
    recommendations_count = models.IntegerField(default=0)
    findings = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Peer Review')
        verbose_name_plural = _('Peer Reviews')
        ordering = ['-scheduled_date']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class MortalityReview(BaseModel):
    """Mortality and Morbidity (M&M) reviews."""
    class ReviewStatus(models.TextChoices):
        SCHEDULED = 'scheduled', _('Scheduled')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='mortality_reviews')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='mortality_reviews')
    case_type = models.CharField(max_length=200)
    incident_date = models.DateTimeField()
    review_date = models.DateTimeField()
    department = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.SCHEDULED)
    summary = models.TextField()
    root_cause = models.TextField(blank=True)
    attendees = models.JSONField(default=list)
    lessons_learned = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    action_items = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Mortality Review')
        verbose_name_plural = _('Mortality Reviews')
        ordering = ['-incident_date']

    def __str__(self):
        return f"M&M: {self.patient.get_full_name()} - {self.case_type}"


class ComplianceScore(BaseModel):
    """Clinical protocol compliance tracking."""
    class ProtocolType(models.TextChoices):
        ANTIBIOTIC_STEWARDSHIP = 'antibiotic_stewardship', _('Antibiotic Stewardship')
        SURGICAL_SAFETY = 'surgical_safety', _('Surgical Safety Checklist')
        BLOOD_TRANSFUSION = 'blood_transfusion', _('Blood Transfusion Protocol')
        INFECTION_CONTROL = 'infection_control', _('Infection Control Measures')
        MEDICATION_RECONCILIATION = 'medication_reconciliation', _('Medication Reconciliation')
        PAIN_MANAGEMENT = 'pain_management', _('Pain Management Protocol')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='compliance_scores')
    protocol = models.CharField(max_length=50, choices=ProtocolType.choices)
    score = models.FloatField()
    target = models.FloatField()
    department = models.CharField(max_length=100, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    findings = models.JSONField(default=list, blank=True)
    improvement_areas = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Compliance Score')
        verbose_name_plural = _('Compliance Scores')
        ordering = ['-period_end', 'protocol']
        unique_together = ['tenant', 'protocol', 'department', 'period_start', 'period_end']

    def __str__(self):
        dept = f" ({self.department})" if self.department else ""
        return f"{self.get_protocol_display()}{dept}: {self.score}%"
