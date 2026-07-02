from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField

from core.models import BaseModel
from tenants.models import Tenant, TenantUser
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


class Admission(BaseModel):
    """Admission request and in-patient admission workflow."""
    class AdmissionStatus(models.TextChoices):
        REQUESTED = 'Requested', _('Requested')
        APPROVED = 'Approved', _('Approved')
        ADMITTED = 'Admitted', _('Admitted')
        DISCHARGED = 'Discharged', _('Discharged')
        TRANSFERRED = 'Transferred', _('Transferred')
        REJECTED = 'Rejected', _('Rejected')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='admissions')
    request_id = models.CharField(max_length=50, unique=True, blank=True)
    patient_id = models.CharField(max_length=50)
    patient_name = models.CharField(max_length=200)
    request_date = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=100, default='Direct Admission')
    diagnosis = models.TextField(blank=True)
    preferred_ward_type = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=20, default='Medium')
    status = models.CharField(max_length=20, choices=AdmissionStatus.choices, default=AdmissionStatus.REQUESTED)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    ward_id = models.CharField(max_length=50, blank=True)
    bed_id = models.CharField(max_length=50, blank=True)
    consultant_name = models.CharField(max_length=200, blank=True)
    consultant_specialty = models.CharField(max_length=200, blank=True)
    expected_stay = models.PositiveIntegerField(default=0)
    planned_discharge_date = models.DateTimeField(null=True, blank=True)
    actual_stay = models.PositiveIntegerField(null=True, blank=True)
    date_of_admission = models.DateTimeField(null=True, blank=True)
    discharge_date = models.DateTimeField(null=True, blank=True)
    discharge_summary = models.JSONField(default=dict, blank=True)
    transfer_history = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Admission')
        verbose_name_plural = _('Admissions')
        ordering = ['-request_date']
        indexes = [
            models.Index(fields=['tenant', 'status', '-request_date']),
            models.Index(fields=['tenant', 'patient_id']),
        ]

    def __str__(self):
        return f"{self.patient_name} ({self.status})"

    @property
    def requestId(self):
        return self.request_id

    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = f"REQ{self.id or '0'}"
        super().save(*args, **kwargs)


class DutyRoster(BaseModel):
    """Duty roster records for a department and month."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='duty_rosters')
    roster_id = models.CharField(max_length=50, unique=True, blank=True)
    month = models.CharField(max_length=50)
    year = models.PositiveIntegerField(default=timezone.now().year)
    department = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default='Draft')

    class Meta:
        verbose_name = _('Duty Roster')
        verbose_name_plural = _('Duty Rosters')
        ordering = ['-year', '-created_at']

    def save(self, *args, **kwargs):
        if not self.roster_id:
            self.roster_id = f"ROSTER{self.id or '0'}"
        super().save(*args, **kwargs)


class DutyAssignment(BaseModel):
    """Single staff assignment inside a duty roster."""
    roster = models.ForeignKey(DutyRoster, on_delete=models.CASCADE, related_name='assignments')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='duty_assignments')
    date = models.DateField()
    duty_type = models.CharField(max_length=100)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date', 'start_time']


class LeaveRequest(BaseModel):
    """Leave requests raised by staff."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leave_requests')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='leave_requests')
    leave_type = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='Pending')
    approved_by = models.CharField(max_length=200, blank=True)
    approval_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class OvertimeRecord(BaseModel):
    """Overtime entry captured for staff."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='overtime_records')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='overtime_records')
    date = models.DateField()
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='Pending')
    approved_by = models.CharField(max_length=200, blank=True)
    rate = models.CharField(max_length=20, default='1.5x')

    class Meta:
        ordering = ['-date', '-created_at']


class PerformanceAppraisal(BaseModel):
    """Annual performance appraisal for staff members."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='performance_appraisals')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='performance_appraisals')
    appraisal_year = models.PositiveIntegerField(default=timezone.now().year)
    period = models.CharField(max_length=100, blank=True)
    rater = models.CharField(max_length=200, blank=True)
    rater_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='appraisals_created')
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    clinical_excellence = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    patient_care = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    teamwork = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    leadership = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    continuous_learning = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    overall_comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='Completed')
    date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-appraisal_year', '-created_at']


class PerformanceAudit(BaseModel):
    """Clinical performance audit records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='performance_audits')
    department = models.CharField(max_length=100)
    audit_type = models.CharField(max_length=100)
    auditor = models.CharField(max_length=200, blank=True)
    auditor_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='audits_conducted')
    audit_date = models.DateField()
    cases_reviewed = models.PositiveIntegerField(default=0)
    compliance_rate = models.CharField(max_length=20, blank=True)
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Performance Audit')
        verbose_name_plural = _('Performance Audits')
        ordering = ['-audit_date', '-created_at']


class ResearchOutput(BaseModel):
    """Research publication and output summary."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='research_outputs')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='research_outputs')
    title = models.CharField(max_length=300)
    publication_type = models.CharField(max_length=100, blank=True)
    journal_name = models.CharField(max_length=200, blank=True)
    publication_date = models.DateField()
    authors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=100, blank=True)
    citation_count = models.PositiveIntegerField(default=0)
    abstract = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Research Output')
        verbose_name_plural = _('Research Outputs')
        ordering = ['-publication_date', '-created_at']


class TeachingActivity(BaseModel):
    """Teaching, continued medical education, and training sessions."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='teaching_activities')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='teaching_activities')
    month = models.CharField(max_length=100)
    topic = models.CharField(max_length=200)
    hours_delivered = models.PositiveIntegerField(default=0)
    students_count = models.PositiveIntegerField(default=0)
    feedback_score = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    class Meta:
        verbose_name = _('Teaching Activity')
        verbose_name_plural = _('Teaching Activities')
        ordering = ['-created_at']


class SatisfactionSurvey(BaseModel):
    """Patient satisfaction survey results."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='satisfaction_surveys')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='satisfaction_surveys')
    survey_date = models.DateField()
    total_feedback = models.PositiveIntegerField(default=0)
    average_score = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    clinical_care = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    communication = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    responsiveness = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    professionalism = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    overall_satisfaction = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    comments = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Satisfaction Survey')
        verbose_name_plural = _('Satisfaction Surveys')
        ordering = ['-survey_date', '-created_at']


class PerformanceIncident(BaseModel):
    """Staff incident and investigation records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='performance_incidents')
    staff_id = models.CharField(max_length=100)
    staff_name = models.CharField(max_length=200, blank=True)
    staff_user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='performance_incidents')
    incident_type = models.CharField(max_length=100)
    reported_date = models.DateField()
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=50, default='Medium')
    investigation_status = models.CharField(max_length=50, default='Open')
    root_cause_analysis = models.TextField(blank=True)
    action_taken = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Performance Incident')
        verbose_name_plural = _('Performance Incidents')
        ordering = ['-reported_date', '-created_at']


class EmergencyCall(BaseModel):
    """Emergency calls received through the response management workflow."""
    class EmergencySeverity(models.TextChoices):
        CRITICAL = 'Critical', _('Critical')
        HIGH = 'High', _('High')
        MEDIUM = 'Medium', _('Medium')
        LOW = 'Low', _('Low')

    class EmergencyStatus(models.TextChoices):
        RECEIVED = 'Received', _('Received')
        DISPATCHED = 'Dispatched', _('Dispatched')
        EN_ROUTE = 'En Route', _('En Route')
        COMPLETED = 'Completed', _('Completed')
        CANCELLED = 'Cancelled', _('Cancelled')

    call_id = models.CharField(max_length=50, unique=True, blank=True)
    caller_name = models.CharField(max_length=200, blank=True)
    caller_phone = models.CharField(max_length=50, blank=True)
    severity = models.CharField(max_length=20, choices=EmergencySeverity.choices, default=EmergencySeverity.MEDIUM)
    status = models.CharField(max_length=20, choices=EmergencyStatus.choices, default=EmergencyStatus.RECEIVED)
    incident_type = models.CharField(max_length=100, blank=True)
    incident_description = models.TextField(blank=True)
    patient_name = models.CharField(max_length=200, blank=True)
    patient_details = models.JSONField(default=dict, blank=True)
    incident_location = models.JSONField(default=dict, blank=True)
    dispatched_ambulance = models.CharField(max_length=100, blank=True)
    response_time = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    communications = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Emergency Call')
        verbose_name_plural = _('Emergency Calls')
        ordering = ['-created_at']

    def __str__(self):
        return self.call_id or self.incident_type or 'Emergency Call'

    def save(self, *args, **kwargs):
        if not self.call_id:
            self.call_id = f"CALL{self.id or '0'}"
        super().save(*args, **kwargs)


class AmbulanceMission(BaseModel):
    """Ambulance dispatch and tracking mission records."""
    class MissionStatus(models.TextChoices):
        DISPATCHED = 'Dispatched', _('Dispatched')
        EN_ROUTE = 'En Route', _('En Route')
        ON_SCENE = 'On Scene', _('On Scene')
        TRANSPORTING = 'Transporting', _('Transporting')
        COMPLETED = 'Completed', _('Completed')
        CANCELLED = 'Cancelled', _('Cancelled')

    mission_id = models.CharField(max_length=50, unique=True, blank=True)
    ambulance_id = models.CharField(max_length=100, blank=True)
    incident_type = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=20, default='Medium')
    status = models.CharField(max_length=20, choices=MissionStatus.choices, default=MissionStatus.DISPATCHED)
    patient_info = models.JSONField(default=dict, blank=True)
    pickup_location = models.JSONField(default=dict, blank=True)
    destination = models.JSONField(default=dict, blank=True)
    crew = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    dispatched_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Ambulance Mission')
        verbose_name_plural = _('Ambulance Missions')
        ordering = ['-dispatched_at']

    def __str__(self):
        return self.mission_id or self.ambulance_id or 'Ambulance Mission'

    def save(self, *args, **kwargs):
        if not self.mission_id:
            self.mission_id = f"MISS{self.id or '0'}"
        super().save(*args, **kwargs)


class ReferralRequest(BaseModel):
    """Inter-facility referral and transport requests."""
    class ReferralStatus(models.TextChoices):
        PENDING = 'Pending', _('Pending')
        APPROVED = 'Approved', _('Approved')
        IN_TRANSIT = 'In Transit', _('In Transit')
        ARRIVED = 'Arrived', _('Arrived')
        COMPLETED = 'Completed', _('Completed')

    referral_id = models.CharField(max_length=50, unique=True, blank=True)
    patient_name = models.CharField(max_length=200, blank=True)
    patient_age = models.PositiveIntegerField(default=0)
    patient_gender = models.CharField(max_length=20, blank=True)
    referral_type = models.CharField(max_length=100, blank=True)
    referral_reason = models.TextField(blank=True)
    referring_facility = models.JSONField(default=dict, blank=True)
    receiving_facility = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=ReferralStatus.choices, default=ReferralStatus.PENDING)
    ambulance_id = models.CharField(max_length=100, blank=True)
    referral_date = models.DateTimeField(default=timezone.now)
    arrival_time = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_medical_evacuation = models.BooleanField(default=False)
    funding_source = models.CharField(max_length=100, blank=True)
    origin_country = models.CharField(max_length=100, blank=True)
    destination_country = models.CharField(max_length=100, blank=True)
    transport_mode = models.CharField(max_length=100, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transfer_compliance = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _('Referral Request')
        verbose_name_plural = _('Referral Requests')
        ordering = ['-referral_date']

    def __str__(self):
        return self.referral_id or self.patient_name or 'Referral Request'

    def save(self, *args, **kwargs):
        if not self.referral_id:
            self.referral_id = f"REF{self.id or '0'}"
        super().save(*args, **kwargs)


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
