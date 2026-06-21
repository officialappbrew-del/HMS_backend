from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient, PatientVisit


class ConsultationNote(BaseModel):
    """Clinical consultation notes (SOAP format)."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='consultation_notes')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='consultation_notes')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consultation_notes')
    
    # Subjective (What the patient says)
    subjective = models.TextField(blank=True)  # Chief complaint, HPI, ROS, etc.
    
    # Objective (What you find)
    objective = models.TextField(blank=True)  # Physical exam, vital signs, etc.
    
    # Assessment (What you think)
    assessment = models.TextField(blank=True)  # Diagnosis, differentials
    diagnosis_codes = models.JSONField(default=list, blank=True)  # ICD-10 codes
    differential_diagnosis = models.TextField(blank=True)
    
    # Plan (What you will do)
    plan = models.TextField(blank=True)  # Treatment plan, investigations, follow-up
    
    # Doctor Information
    doctor = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                              limit_choices_to={'role': 'doctor'})
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_final = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Consultation Note for {self.patient.get_full_name()} - {self.created_at.date()}"
    
    class Meta:
        verbose_name = _('Consultation Note')
        verbose_name_plural = _('Consultation Notes')
        ordering = ['-created_at']


class Prescription(BaseModel):
    """Medical prescriptions."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='prescriptions')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='prescriptions')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions')
    
    # Prescription Details
    drug_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)  # e.g., 500mg
    frequency = models.CharField(max_length=100)  # e.g., Twice daily
    duration = models.IntegerField(help_text='Duration in days')
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
    
    # Instructions
    instructions = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('prescribed', 'Prescribed'),
        ('dispensed', 'Dispensed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed')
    ], default='prescribed')
    
    # Prescriber
    prescribed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                     limit_choices_to={'role': 'doctor'})
    prescribed_date = models.DateTimeField(auto_now_add=True)
    
    # Pharmacy
    dispensed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    limit_choices_to={'role': 'pharmacist'}, related_name='dispensed_prescriptions')
    dispensed_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.drug_name} for {self.patient.get_full_name()}"
    
    class Meta:
        verbose_name = _('Prescription')
        verbose_name_plural = _('Prescriptions')
        ordering = ['-prescribed_date']


class VitalSign(BaseModel):
    """Patient vital signs recordings."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vital_signs')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='vital_signs')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='vital_sign_records',
                             null=True, blank=True)
    
    # Vital Signs
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse = models.IntegerField(null=True, blank=True)  # bpm
    respiratory_rate = models.IntegerField(null=True, blank=True)  # breaths/min
    blood_pressure_systolic = models.IntegerField(null=True, blank=True)  # mmHg
    blood_pressure_diastolic = models.IntegerField(null=True, blank=True)  # mmHg
    oxygen_saturation = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)  # %
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # kg
    height = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # meters
    bmi = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # kg/m²
    
    # Additional Measurements
    pain_score = models.IntegerField(null=True, blank=True, choices=[
        (0, '0 - No pain'),
        (1, '1'),
        (2, '2 - Mild'),
        (3, '3'),
        (4, '4 - Moderate'),
        (5, '5'),
        (6, '6'),
        (7, '7 - Severe'),
        (8, '8'),
        (9, '9'),
        (10, '10 - Worst possible')
    ])
    
    # Recorded By
    recorded_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                   limit_choices_to={'role__in': ['nurse', 'doctor']})
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"Vitals for {self.patient.get_full_name()} at {self.recorded_at}"
    
    class Meta:
        verbose_name = _('Vital Sign')
        verbose_name_plural = _('Vital Signs')
        ordering = ['-recorded_at']
    
    def save(self, *args, **kwargs):
        # Calculate BMI if height and weight are provided
        if self.height and self.weight and self.height > 0:
            self.bmi = self.weight / (self.height * self.height)
        
        # Calculate blood pressure category
        if self.blood_pressure_systolic and self.blood_pressure_diastolic:
            self.blood_pressure_category = self.get_blood_pressure_category()
        
        super().save(*args, **kwargs)
    
    def get_blood_pressure_category(self):
        """Get blood pressure category based on guidelines."""
        systolic = self.blood_pressure_systolic
        diastolic = self.blood_pressure_diastolic
        
        if systolic < 120 and diastolic < 80:
            return 'normal'
        elif 120 <= systolic <= 129 and diastolic < 80:
            return 'elevated'
        elif 130 <= systolic <= 139 or 80 <= diastolic <= 89:
            return 'stage1'
        elif systolic >= 140 or diastolic >= 90:
            return 'stage2'
        elif systolic > 180 or diastolic > 120:
            return 'hypertensive_crisis'
        return 'unknown'