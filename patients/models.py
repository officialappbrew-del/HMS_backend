from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.contrib.auth.hashers import make_password, check_password
import uuid

from core.models import BaseModel, EncryptedField
from tenants.models import Tenant


class Patient(BaseModel):
    """Patient model for healthcare facilities."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patients')
    
    # Identification
    hospital_number = models.CharField(max_length=50, unique=True)
    login_id = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True)
    password = models.CharField(max_length=128, blank=True)
    nhis_number = models.CharField(max_length=50, blank=True, null=True)
    nin = models.CharField(max_length=11, blank=True, null=True, verbose_name='National Identity Number')
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    age = models.IntegerField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('unknown', 'Unknown')
    ])
    marital_status = models.CharField(max_length=20, choices=[
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('separated', 'Separated')
    ], default='single')
    
    # Contact Information
    phone = models.CharField(max_length=15, validators=[
        RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")
    ])
    phone2 = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, default='Rivers')
    lga = models.CharField(max_length=100, blank=True, verbose_name='Local Government Area')
    country = models.CharField(max_length=100, default='Nigeria')
    
    # Next of Kin
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_relationship = models.CharField(max_length=50, blank=True)
    next_of_kin_phone = models.CharField(max_length=15, blank=True)
    next_of_kin_address = models.TextField(blank=True)
    
    # Medical Information
    blood_group = models.CharField(max_length=10, choices=[  # Changed from 5 to 10
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('unknown', 'Unknown')
    ], default='unknown')
    genotype = models.CharField(max_length=10, choices=[  # Changed from 5 to 10
        ('AA', 'AA'), ('AS', 'AS'), ('SS', 'SS'),
        ('AC', 'AC'), ('SC', 'SC'),
        ('unknown', 'Unknown')
    ], default='unknown')
    
    # Medical History
    known_allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    surgical_history = models.TextField(blank=True)
    family_history = models.TextField(blank=True)
    
    # Insurance Information
    has_insurance = models.BooleanField(default=False)
    insurance_company = models.CharField(max_length=200, blank=True)
    insurance_policy_number = models.CharField(max_length=100, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    
    # Nigerian Specific
    occupation = models.CharField(max_length=200, blank=True)
    religion = models.CharField(max_length=100, blank=True)
    ethnicity = models.CharField(max_length=100, blank=True)
    language_spoken = models.CharField(max_length=200, default='English')
    
    # Status
    patient_status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('deceased', 'Deceased'),
        ('transferred', 'Transferred')
    ], default='active')
    
    # Additional Information
    photo = models.ImageField(upload_to='patient_photos/', null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Metadata
    registered_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='registered_patients')
    registration_date = models.DateTimeField(auto_now_add=True)
    last_visit = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.hospital_number})"
    
    class Meta:
        verbose_name = _('Patient')
        verbose_name_plural = _('Patients')
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['hospital_number']),
            models.Index(fields=['nhis_number']),
            models.Index(fields=['last_name', 'first_name']),
        ]
    
    def save(self, *args, **kwargs):
        # Generate hospital number if not provided
        if not self.hospital_number:
            self.hospital_number = self.generate_hospital_number()

        # Use hospital number as the default login identifier if needed.
        if not self.login_id:
            self.login_id = self.hospital_number
        
        # Calculate age from date of birth
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year
            if today.month < self.date_of_birth.month or (today.month == self.date_of_birth.month and today.day < self.date_of_birth.day):
                age -= 1
            self.age = age
        
        super().save(*args, **kwargs)
    
    def generate_hospital_number(self):
        """Generate unique hospital number."""
        import random
        import string
        
        tenant_code = self.tenant.code[:3].upper()
        year = timezone.now().year
        random_part = ''.join(random.choices(string.digits, k=6))
        return f"{tenant_code}-{year}-{random_part}"
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def get_full_name(self):
        """Get patient's full name."""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def get_age_display(self):
        """Get age display with years and months if applicable."""
        if not self.date_of_birth:
            return "Unknown"
        
        today = timezone.now().date()
        age_years = today.year - self.date_of_birth.year
        
        if today.month < self.date_of_birth.month or (today.month == self.date_of_birth.month and today.day < self.date_of_birth.day):
            age_years -= 1
        
        return f"{age_years} years"


class PatientVisit(BaseModel):
    """Patient visit/encounter record."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patient_visits')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    
    # Visit Information
    visit_number = models.CharField(max_length=50, unique=True)
    visit_type = models.CharField(max_length=20, choices=[
        ('opd', 'Outpatient (OPD)'),
        ('ipd', 'Inpatient (IPD)'),
        ('emergency', 'Emergency'),
        ('followup', 'Follow-up'),
        ('antenatal', 'Antenatal'),
        ('immunization', 'Immunization'),
        ('dental', 'Dental'),
        ('eye', 'Eye Clinic'),
    ], default='opd')
    
    # Clinical Information
    chief_complaint = models.TextField()
    history_of_present_illness = models.TextField(blank=True)
    vital_signs = models.JSONField(default=dict, blank=True)  # {bp: '120/80', temp: '37', pulse: '72', ...}
    triage_category = models.CharField(max_length=20, choices=[
        ('red', 'Red - Immediate'),
        ('yellow', 'Yellow - Urgent'),
        ('green', 'Green - Delayed'),
        ('blue', 'Blue - Minimal')
    ], default='green')
    
    # Service Details
    department = models.ForeignKey('tenants.Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='patient_visits')
    doctor = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True, 
                              limit_choices_to={'role': 'doctor'}, related_name='doctor_visits')
    nurse = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                            limit_choices_to={'role': 'nurse'}, related_name='nurse_visits')
    
    # Status
    visit_status = models.CharField(max_length=20, choices=[
        ('registered', 'Registered'),
        ('triaged', 'Triaged'),
        ('waiting', 'Waiting for Doctor'),
        ('in_consultation', 'In Consultation'),
        ('awaiting_lab', 'Awaiting Lab Results'),
        ('awaiting_pharmacy', 'Awaiting Pharmacy'),
        ('billing', 'Billing'),
        ('completed', 'Completed'),
        ('admitted', 'Admitted'),
        ('referred', 'Referred'),
        ('discharged', 'Discharged'),
    ], default='registered')
    
    # Timing
    checkin_time = models.DateTimeField(auto_now_add=True)
    triage_time = models.DateTimeField(null=True, blank=True)
    consultation_start_time = models.DateTimeField(null=True, blank=True)
    consultation_end_time = models.DateTimeField(null=True, blank=True)
    discharge_time = models.DateTimeField(null=True, blank=True)
    
    # Additional Information
    referral_from = models.CharField(max_length=200, blank=True)
    referral_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"Visit {self.visit_number} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Patient Visit')
        verbose_name_plural = _('Patient Visits')
        ordering = ['-checkin_time']
    
    def save(self, *args, **kwargs):
        # Generate visit number if not provided
        if not self.visit_number:
            self.visit_number = self.generate_visit_number()
        super().save(*args, **kwargs)
    
    def generate_visit_number(self):
        """Generate unique visit number."""
        import random
        import string
        
        date_str = timezone.now().strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.digits, k=6))
        return f"V-{date_str}-{random_part}"
    
    def get_waiting_time(self):
        """Calculate waiting time."""
        if self.consultation_start_time and self.checkin_time:
            return self.consultation_start_time - self.checkin_time
        elif self.triage_time and self.checkin_time:
            return self.triage_time - self.checkin_time
        return None


class PatientDocument(BaseModel):
    """Patient documents and records."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patient_documents')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='documents')
    
    # Document Information
    document_type = models.CharField(max_length=50, choices=[
        ('identification', 'Identification'),
        ('medical_report', 'Medical Report'),
        ('lab_result', 'Lab Result'),
        ('radiology', 'Radiology Report'),
        ('prescription', 'Prescription'),
        ('consent_form', 'Consent Form'),
        ('insurance', 'Insurance Document'),
        ('referral', 'Referral Letter'),
        ('discharge', 'Discharge Summary'),
        ('other', 'Other')
    ])
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # File Information
    file = models.FileField(upload_to='patient_documents/')
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.IntegerField(blank=True, null=True)  # in bytes
    file_type = models.CharField(max_length=100, blank=True)
    
    # Metadata
    uploaded_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    upload_date = models.DateTimeField(auto_now_add=True)
    document_date = models.DateField(null=True, blank=True)
    
    # Security
    is_confidential = models.BooleanField(default=False)
    access_restricted = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.title} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Patient Document')
        verbose_name_plural = _('Patient Documents')
        ordering = ['-upload_date']
    
    def save(self, *args, **kwargs):
        # Extract file information
        if self.file:
            self.file_name = self.file.name
            self.file_size = self.file.size
            import os
            self.file_type = os.path.splitext(self.file.name)[1].lower()
        
        super().save(*args, **kwargs)


class PatientAllergy(BaseModel):
    """Patient allergies."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patient_allergies')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='allergies')
    
    # Allergy Information
    allergen = models.CharField(max_length=200)  # e.g., Penicillin, Peanuts
    allergy_type = models.CharField(max_length=50, choices=[
        ('drug', 'Drug'),
        ('food', 'Food'),
        ('environmental', 'Environmental'),
        ('insect', 'Insect'),
        ('other', 'Other')
    ])
    reaction = models.TextField()  # e.g., Rash, Anaphylaxis
    severity = models.CharField(max_length=20, choices=[
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('severe', 'Severe'),
        ('life_threatening', 'Life-threatening')
    ])
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('resolved', 'Resolved'),
        ('uncertain', 'Uncertain')
    ], default='active')
    
    # Dates
    first_noted = models.DateField(null=True, blank=True)
    last_occurrence = models.DateField(null=True, blank=True)
    
    # Additional Information
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_allergies')
    verified_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.allergen} allergy - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Patient Allergy')
        verbose_name_plural = _('Patient Allergies')
        ordering = ['-severity', 'allergen']
        unique_together = ['patient', 'allergen']


class PatientMedication(BaseModel):
    """Current medications for patients."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patient_medications')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='patient_medications')
    
    # Medication Information
    medication_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)  # e.g., 500mg
    frequency = models.CharField(max_length=100)  # e.g., Twice daily
    route = models.CharField(max_length=50, choices=[
        ('oral', 'Oral'),
        ('iv', 'IV'),
        ('im', 'IM'),
        ('sc', 'SC'),
        ('topical', 'Topical'),
        ('inhalation', 'Inhalation'),
        ('rectal', 'Rectal'),
        ('vaginal', 'Vaginal'),
        ('otic', 'Otic'),
        ('ophthalmic', 'Ophthalmic')
    ], default='oral')
    
    # Prescription Details
    prescribed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, 
                                     limit_choices_to={'role': 'doctor'}, related_name='prescribed_medications')
    prescription_date = models.DateField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('discontinued', 'Discontinued'),
        ('on_hold', 'On Hold')
    ], default='active')
    
    # Additional Information
    reason = models.TextField(blank=True)  # Reason for medication
    instructions = models.TextField(blank=True)  # Special instructions
    side_effects = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.medication_name} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Patient Medication')
        verbose_name_plural = _('Patient Medications')
        ordering = ['-start_date']


class Appointment(BaseModel):
    """Patient appointments."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='appointments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    
    # Appointment Details
    appointment_number = models.CharField(max_length=50, unique=True)
    appointment_type = models.CharField(max_length=50, choices=[
        ('consultation', 'Consultation'),
        ('followup', 'Follow-up'),
        ('procedure', 'Procedure'),
        ('test', 'Test/Investigation'),
        ('review', 'Review'),
        ('immunization', 'Immunization'),
        ('antenatal', 'Antenatal'),
        ('other', 'Other')
    ], default='consultation')
    
    # Schedule
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    expected_duration = models.IntegerField(default=30, help_text='Duration in minutes')
    
    # Staff Assignment
    doctor = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                              limit_choices_to={'role': 'doctor'}, related_name='doctor_appointments')
    department = models.ForeignKey('tenants.Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments')
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
        ('rescheduled', 'Rescheduled')
    ], default='scheduled')
    
    # Timing
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    
    # Additional Information
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_date = models.DateTimeField(null=True, blank=True)
    
    # Audit
    created_by = models.ForeignKey(
        'tenants.TenantUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_appointments'
    )
    updated_by = models.ForeignKey(
        'tenants.TenantUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_appointments'
    )
    
    def __str__(self):
        return f"Appointment {self.appointment_number} - {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Appointment')
        verbose_name_plural = _('Appointments')
        ordering = ['scheduled_date', 'scheduled_time']
    
    def save(self, *args, **kwargs):
        # Generate appointment number if not provided
        if not self.appointment_number:
            self.appointment_number = self.generate_appointment_number()
        super().save(*args, **kwargs)
    
    def generate_appointment_number(self):
        """Generate unique appointment number."""
        import random
        import string
        
        date_str = self.scheduled_date.strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.digits, k=6))
        return f"APT-{date_str}-{random_part}"
    
    def is_past_due(self):
        """Check if appointment is past due."""
        from django.utils import timezone
        appointment_datetime = timezone.make_aware(
            timezone.datetime.combine(self.scheduled_date, self.scheduled_time)
        )
        return timezone.now() > appointment_datetime and self.status == 'scheduled'