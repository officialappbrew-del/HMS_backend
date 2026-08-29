from django.db import models
from django.utils import timezone

from core.models import BaseModel
from patients.models import Patient
from tenants.models import Tenant, TenantUser
from ward_rounds.models import Ward, Bed


class IPDStay(BaseModel):
    class Status(models.TextChoices):
        PRE_ADMISSION = 'pre_admission', 'Pre-admission'
        WAITING = 'waiting', 'Waiting for bed'
        ADMITTED = 'admitted', 'Admitted'
        DISCHARGED = 'discharged', 'Discharged'
        TRANSFERRED = 'transferred', 'Transferred out'
        DECEASED = 'deceased', 'Deceased'

    class ArrivalMode(models.TextChoices):
        WALK_IN = 'walk_in', 'Walk-in'
        AMBULANCE = 'ambulance', 'Ambulance'
        REFERRAL = 'referral', 'Referral'
        OPD = 'opd', 'OPD transfer'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ipd_stays')
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='ipd_stays')
    admitting_doctor = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='ipd_admissions')
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, null=True, blank=True, related_name='ipd_stays')
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, null=True, blank=True, related_name='ipd_stays')
    admission_number = models.CharField(max_length=40, unique=True, blank=True)
    diagnosis = models.TextField()
    admission_reason = models.TextField(blank=True)
    arrival_mode = models.CharField(max_length=20, choices=ArrivalMode.choices, default=ArrivalMode.WALK_IN)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    emergency = models.BooleanField(default=False)
    pre_authorization_number = models.CharField(max_length=100, blank=True)
    expected_discharge_date = models.DateField(null=True, blank=True)
    admitted_at = models.DateTimeField(null=True, blank=True)
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharge_criteria = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['tenant', 'status']), models.Index(fields=['patient', 'status'])]

    def save(self, *args, **kwargs):
        if not self.admission_number:
            self.admission_number = f'IPD-{timezone.now():%Y%m%d%H%M%S%f}'
        super().save(*args, **kwargs)


class IPDProgressNote(BaseModel):
    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='progress_notes')
    author = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_progress_notes')
    subjective = models.TextField(blank=True)
    objective = models.TextField(blank=True)
    assessment = models.TextField()
    plan = models.TextField()

    class Meta:
        ordering = ['-created_at']


class IntakeOutput(BaseModel):
    class Category(models.TextChoices):
        INTAKE = 'intake', 'Intake'
        OUTPUT = 'output', 'Output'

    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='intake_outputs')
    recorded_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_intake_outputs')
    category = models.CharField(max_length=10, choices=Category.choices)
    item = models.CharField(max_length=100)
    amount_ml = models.DecimalField(max_digits=8, decimal_places=2)
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)


class NursingCarePlan(BaseModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='care_plans')
    created_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='created_ipd_care_plans')
    goal = models.CharField(max_length=255)
    intervention = models.TextField()
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)


class MedicationAdministration(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        GIVEN = 'given', 'Given'
        HELD = 'held', 'Held'
        REFUSED = 'refused', 'Refused'
        OMITTED = 'omitted', 'Omitted'

    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='mar_entries')
    medication_name = models.CharField(max_length=200)
    dose = models.CharField(max_length=100)
    route = models.CharField(max_length=50)
    scheduled_at = models.DateTimeField()
    administered_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    reason = models.TextField(blank=True)
    administered_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='ipd_medication_administrations')


class IPDTransfer(BaseModel):
    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='transfers')
    from_ward = models.ForeignKey(Ward, on_delete=models.PROTECT, null=True, blank=True, related_name='ipd_transfers_from')
    from_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, null=True, blank=True, related_name='ipd_transfers_from')
    to_ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name='ipd_transfers_to')
    to_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='ipd_transfers_to')
    reason = models.TextField()
    escort_details = models.TextField(blank=True)
    transferred_at = models.DateTimeField(default=timezone.now)
    transferred_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_transfers')


class IPDDischarge(BaseModel):
    stay = models.OneToOneField(IPDStay, on_delete=models.PROTECT, related_name='discharge')
    prepared_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_discharges_prepared')
    diagnosis = models.TextField()
    treatment_given = models.TextField(blank=True)
    procedures = models.TextField(blank=True)
    discharge_medications = models.JSONField(default=list, blank=True)
    follow_up_advice = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    billing_cleared = models.BooleanField(default=False)
    summary_signed = models.BooleanField(default=False)
    belongings_returned = models.BooleanField(default=False)
    feedback_score = models.PositiveSmallIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(default=timezone.now)


class IPDClinicalRecord(BaseModel):
    """Structured daily operational records that do not belong in free text."""
    RECORD_TYPES = [
        ('shift_handover', 'Shift handover'), ('wound_care', 'Wound care'),
        ('patient_observation', 'Patient observation'), ('procedure_order', 'Procedure order'),
        ('specialist_referral', 'Specialist referral'), ('leave_of_absence', 'Leave of absence'),
        ('consent', 'Consent'), ('advance_directive', 'Advance directive'),
        ('medico_legal', 'Medico-legal case'),
    ]
    stay = models.ForeignKey(IPDStay, on_delete=models.CASCADE, related_name='clinical_records')
    record_type = models.CharField(max_length=30, choices=RECORD_TYPES)
    created_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_clinical_records')
    status = models.CharField(max_length=30, default='open')
    payload = models.JSONField(default=dict, blank=True)
    attachment = models.FileField(upload_to='ipd/clinical/', blank=True, null=True)


class IPDCharge(BaseModel):
    """Itemized IPD charge captured from clinical activity or nightly accrual."""
    stay = models.ForeignKey(IPDStay, on_delete=models.PROTECT, related_name='charges')
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=40, default='other')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    charge_date = models.DateField(default=timezone.localdate)
    source = models.CharField(max_length=30, default='manual')
    posted_by = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, related_name='ipd_charges_posted')

    @property
    def total(self):
        return self.quantity * self.unit_price


class IPDWaitlist(BaseModel):
    stay = models.OneToOneField(IPDStay, on_delete=models.CASCADE, related_name='waitlist_entry')
    requested_ward_type = models.CharField(max_length=100)
    priority = models.CharField(max_length=20, default='normal')
    notified_at = models.DateTimeField(null=True, blank=True)
