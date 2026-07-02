from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant, TenantUser


class ConsentRecord(BaseModel):
    class ConsentType(models.TextChoices):
        TREATMENT = 'treatment', _('Treatment & Care')
        DATA_PROCESSING = 'data_processing', _('Data Processing')
        RESEARCH = 'research', _('Research Participation')
        MARKETING = 'marketing', _('Marketing Communications')
        THIRD_PARTY = 'third_party', _('Third Party Sharing')

    class ConsentStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        EXPIRED = 'expired', _('Expired')
        WITHDRAWN = 'withdrawn', _('Withdrawn')
        PENDING = 'pending', _('Pending')

    class ConsentMethod(models.TextChoices):
        DIGITAL = 'digital', _('Digital Signature')
        PAPER = 'paper', _('Paper Form')
        VERBAL = 'verbal', _('Verbal Consent')
        IMPLIED = 'implied', _('Implied Consent')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='consent_records')
    patient_id = models.CharField(max_length=50, db_index=True)
    patient_name = models.CharField(max_length=200)
    consent_type = models.CharField(max_length=30, choices=ConsentType.choices)
    purpose = models.TextField()
    data_categories = models.JSONField(default=list, blank=True)
    retention_period = models.CharField(max_length=20, blank=True)
    third_parties = models.JSONField(default=list, blank=True)
    consent_method = models.CharField(max_length=20, choices=ConsentMethod.choices, default=ConsentMethod.DIGITAL)
    witness_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=ConsentStatus.choices, default=ConsentStatus.ACTIVE)
    expiry_date = models.DateField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    recorded_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='consent_records')

    class Meta:
        verbose_name = _('Consent Record')
        verbose_name_plural = _('Consent Records')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'patient_id', 'status']),
            models.Index(fields=['tenant', 'consent_type', 'status']),
        ]

    def __str__(self):
        return f"{self.patient_name} - {self.consent_type} ({self.status})"


class DataSubjectRequest(BaseModel):
    class RequesterType(models.TextChoices):
        DATA_SUBJECT = 'data_subject', _('Data Subject')
        LEGAL_REPRESENTATIVE = 'legal_representative', _('Legal Representative')
        REGULATORY_AUTHORITY = 'regulatory_authority', _('Regulatory Authority')
        OTHER = 'other', _('Other')

    class RequestType(models.TextChoices):
        ACCESS = 'access', _('Right to Access')
        RECTIFICATION = 'rectification', _('Right to Rectification')
        ERASURE = 'erasure', _('Right to Erasure')
        RESTRICTION = 'restriction', _('Right to Restriction')
        PORTABILITY = 'portability', _('Right to Data Portability')
        OBJECT = 'object', _('Right to Object')
        OTHER = 'other', _('Other')

    class RequestStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        UNDER_REVIEW = 'under_review', _('Under Review')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        COMPLETED = 'completed', _('Completed')
        PARTIALLY_COMPLETED = 'partially_completed', _('Partially Completed')

    class Urgency(models.TextChoices):
        NORMAL = 'normal', _('Normal')
        URGENT = 'urgent', _('Urgent')
        CRITICAL = 'critical', _('Critical')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='data_subject_requests')
    requester_type = models.CharField(max_length=30, choices=RequesterType.choices)
    requester_name = models.CharField(max_length=200)
    requester_contact = models.CharField(max_length=200)
    request_type = models.CharField(max_length=30, choices=RequestType.choices)
    data_categories = models.JSONField(default=list, blank=True)
    reason = models.TextField()
    urgency = models.CharField(max_length=20, choices=Urgency.choices, default=Urgency.NORMAL)
    identity_verification = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_time = models.CharField(max_length=50, blank=True)
    response = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests')

    class Meta:
        verbose_name = _('Data Subject Request')
        verbose_name_plural = _('Data Subject Requests')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['tenant', 'request_type', 'status']),
            models.Index(fields=['tenant', 'status', '-submitted_at']),
        ]

    def __str__(self):
        return f"{self.requester_name} - {self.request_type} ({self.status})"


class DataBreach(BaseModel):
    class BreachType(models.TextChoices):
        UNAUTHORIZED_ACCESS = 'unauthorized_access', _('Unauthorized Access')
        DATA_LOSS = 'data_loss', _('Data Loss/Theft')
        HACKING = 'hacking', _('Hacking/Cyber Attack')
        PHYSICAL_THEFT = 'physical_theft', _('Physical Theft')
        ACCIDENTAL_DISCLOSURE = 'accidental_disclosure', _('Accidental Disclosure')
        SYSTEM_FAILURE = 'system_failure', _('System Failure')
        OTHER = 'other', _('Other')

    class Severity(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        CRITICAL = 'critical', _('Critical')

    class BreachStatus(models.TextChoices):
        INVESTIGATING = 'investigating', _('Investigating')
        CONTAINED = 'contained', _('Contained')
        RESOLVED = 'resolved', _('Resolved')
        REPORTED = 'reported', _('Reported to NITDA')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='data_breaches')
    breach_type = models.CharField(max_length=30, choices=BreachType.choices)
    affected_data = models.JSONField(default=list, blank=True)
    affected_individuals = models.PositiveIntegerField(default=0)
    breach_date = models.DateTimeField()
    discovery_date = models.DateTimeField()
    description = models.TextField()
    containment_actions = models.TextField()
    impact_assessment = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=20, choices=BreachStatus.choices, default=BreachStatus.INVESTIGATING)
    reported_to_nitda = models.BooleanField(default=False)
    nitda_report_date = models.DateTimeField(null=True, blank=True)
    notification_sent = models.BooleanField(default=False)
    notifications_sent_count = models.PositiveIntegerField(default=0)
    response_time_hours = models.FloatField(default=0.0)
    investigation_findings = models.TextField(blank=True)
    preventive_actions = models.TextField(blank=True)
    reported_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_breaches')

    class Meta:
        verbose_name = _('Data Breach')
        verbose_name_plural = _('Data Breaches')
        ordering = ['-breach_date']
        indexes = [
            models.Index(fields=['tenant', 'breach_type', '-breach_date']),
            models.Index(fields=['tenant', 'status', '-breach_date']),
        ]

    def __str__(self):
        return f"{self.breach_type} - {self.discovery_date} ({self.status})"


class NDPRAuditLog(BaseModel):
    class ActionType(models.TextChoices):
        CONSENT_CREATED = 'consent_created', _('Consent Created')
        CONSENT_UPDATED = 'consent_updated', _('Consent Updated')
        CONSENT_WITHDRAWN = 'consent_withdrawn', _('Consent Withdrawn')
        DATA_ACCESSED = 'data_accessed', _('Data Accessed')
        DATA_EXPORTED = 'data_exported', _('Data Exported')
        DATA_REQUESTED = 'data_requested', _('Data Requested')
        BREACH_REPORTED = 'breach_reported', _('Breach Reported')
        SETTINGS_UPDATED = 'settings_updated', _('Settings Updated')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ndpr_audit_logs')
    user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='ndpr_audit_logs')
    action = models.CharField(max_length=30, choices=ActionType.choices)
    description = models.TextField()
    resource_type = models.CharField(max_length=50, blank=True)
    resource_id = models.CharField(max_length=50, blank=True)
    patient_id = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _('NDPR Audit Log')
        verbose_name_plural = _('NDPR Audit Logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'action', '-created_at']),
            models.Index(fields=['tenant', 'user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"


class ComplianceReport(BaseModel):
    class ReportType(models.TextChoices):
        CONSENT_AUDIT = 'consent_audit', _('Consent Audit Report')
        DATA_SUBJECT_RIGHTS = 'data_subject_rights', _('Data Subject Rights Report')
        BREACH_INCIDENT = 'breach_incident', _('Breach Incident Report')
        ANNUAL_COMPLIANCE = 'annual_compliance', _('Annual NDPR Compliance')
        TRAINING_COMPLIANCE = 'training_compliance', _('Training Compliance Report')
        THIRD_PARTY_REVIEW = 'third_party_review', _('Third Party Review')

    class ReportStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        GENERATED = 'generated', _('Generated')
        PUBLISHED = 'published', _('Published')
        ARCHIVED = 'archived', _('Archived')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='compliance_reports')
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.DRAFT)
    generated_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_reports')
    file_path = models.CharField(max_length=500, blank=True)
    summary = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _('Compliance Report')
        verbose_name_plural = _('Compliance Reports')
        ordering = ['-period_end', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'report_type', '-period_end']),
        ]

    def __str__(self):
        return f"{self.title} ({self.period_start} to {self.period_end})"
