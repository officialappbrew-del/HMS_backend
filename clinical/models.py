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
    
    subjective = models.TextField(blank=True)
    objective = models.TextField(blank=True)
    assessment = models.TextField(blank=True)
    diagnosis_codes = models.JSONField(default=list, blank=True)
    differential_diagnosis = models.TextField(blank=True)
    plan = models.TextField(blank=True)
    
    doctor = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                              limit_choices_to={'role': 'doctor'})
    
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
    
    drug_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    route = models.CharField(max_length=50, choices=[
        ('oral', 'Oral'), ('iv', 'IV'), ('im', 'IM'), ('sc', 'SC'),
        ('topical', 'Topical'), ('inhalation', 'Inhalation'), ('rectal', 'Rectal'),
        ('vaginal', 'Vaginal'), ('otic', 'Otic'), ('ophthalmic', 'Ophthalmic')
    ], default='oral')
    
    instructions = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=[
        ('prescribed', 'Prescribed'), ('dispensed', 'Dispensed'),
        ('cancelled', 'Cancelled'), ('completed', 'Completed')
    ], default='prescribed')
    
    prescribed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                     limit_choices_to={'role': 'doctor'})
    prescribed_date = models.DateTimeField(auto_now_add=True)
    
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
    
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse = models.IntegerField(null=True, blank=True)
    respiratory_rate = models.IntegerField(null=True, blank=True)
    blood_pressure_systolic = models.IntegerField(null=True, blank=True)
    blood_pressure_diastolic = models.IntegerField(null=True, blank=True)
    oxygen_saturation = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    bmi = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    
    pain_score = models.IntegerField(null=True, blank=True, choices=[
        (0, '0'), (1, '1'), (2, '2 - Mild'), (3, '3'), (4, '4 - Moderate'),
        (5, '5'), (6, '6'), (7, '7 - Severe'), (8, '8'), (9, '9'), (10, '10 - Worst')
    ])
    consciousness = models.CharField(max_length=20, choices=[
        ('Alert', 'Alert'), ('Voice', 'Responds to Voice'),
        ('Pain', 'Responds to Pain'), ('Unresponsive', 'Unresponsive')
    ], default='Alert', blank=True)
    blood_glucose = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    
    recorded_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                   limit_choices_to={'role__in': ['nurse', 'doctor']})
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"Vitals for {self.patient.get_full_name()} at {self.recorded_at}"
    
    class Meta:
        verbose_name = _('Vital Sign')
        verbose_name_plural = _('Vital Signs')
        ordering = ['-recorded_at']
    
    def save(self, *args, **kwargs):
        if self.height and self.weight and self.height > 0:
            self.bmi = self.weight / (self.height * self.height)
        if self.blood_pressure_systolic and self.blood_pressure_diastolic:
            self.blood_pressure_category = self.get_blood_pressure_category()
        super().save(*args, **kwargs)
    
    def get_blood_pressure_category(self):
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


class EarlyWarningScore(BaseModel):
    """NEWS2 Early Warning Score calculated from vital signs."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='early_warning_scores')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='early_warning_scores')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='early_warning_scores',
                             null=True, blank=True)
    vital_sign = models.ForeignKey(VitalSign, on_delete=models.CASCADE, related_name='early_warning_scores')
    
    respiration_score = models.IntegerField(default=0)
    oxygen_score = models.IntegerField(default=0)
    temperature_score = models.IntegerField(default=0)
    systolic_bp_score = models.IntegerField(default=0)
    heart_rate_score = models.IntegerField(default=0)
    consciousness_score = models.IntegerField(default=0)
    total_score = models.IntegerField(default=0)
    
    risk_level = models.CharField(max_length=20, choices=[
        ('low', 'Low (0-4)'), ('medium', 'Medium (5-6)'), ('high', 'High (7+)')
    ], default='low')
    
    calculated_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                     limit_choices_to={'role__in': ['nurse', 'doctor']})
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"EWS for {self.patient.get_full_name()} - Score: {self.total_score}"
    
    class Meta:
        verbose_name = _('Early Warning Score')
        verbose_name_plural = _('Early Warning Scores')
        ordering = ['-calculated_at']
    
    @staticmethod
    def calculate_newts2_score(respiration_rate, oxygen_saturation, temperature, systolic_bp, heart_rate, consciousness):
        score = 0
        
        if respiration_rate <= 8 or respiration_rate >= 25:
            score += 3
        elif 21 <= respiration_rate <= 24:
            score += 2
        elif 9 <= respiration_rate <= 11:
            score += 1
        
        if oxygen_saturation <= 91:
            score += 3
        elif 92 <= oxygen_saturation <= 93:
            score += 2
        elif 94 <= oxygen_saturation <= 95:
            score += 1
        
        if temperature <= 35.0:
            score += 3
        elif temperature >= 39.1:
            score += 2
        elif 38.1 <= temperature <= 39.0:
            score += 1
        
        if systolic_bp <= 90 or systolic_bp >= 220:
            score += 3
        elif 101 <= systolic_bp <= 110:
            score += 2
        elif 111 <= systolic_bp <= 219:
            score += 1
        
        if heart_rate <= 40 or heart_rate >= 131:
            score += 3
        elif 111 <= heart_rate <= 130:
            score += 2
        elif (41 <= heart_rate <= 50) or (91 <= heart_rate <= 110):
            score += 1
        
        if consciousness != 'Alert':
            score += 3
        
        risk_level = 'high' if score >= 7 else 'medium' if score >= 5 else 'low'
        
        return {
            'total': score,
            'risk_level': risk_level,
            'respiration_score': 3 if (respiration_rate <= 8 or respiration_rate >= 25) else 2 if (21 <= respiration_rate <= 24) else 1 if (9 <= respiration_rate <= 11) else 0,
            'oxygen_score': 3 if oxygen_saturation <= 91 else 2 if (92 <= oxygen_saturation <= 93) else 1 if (94 <= oxygen_saturation <= 95) else 0,
            'temperature_score': 3 if temperature <= 35.0 else 2 if temperature >= 39.1 else 1 if (38.1 <= temperature <= 39.0) else 0,
            'systolic_bp_score': 3 if (systolic_bp <= 90 or systolic_bp >= 220) else 2 if (101 <= systolic_bp <= 110) else 1 if (111 <= systolic_bp <= 219) else 0,
            'heart_rate_score': 3 if (heart_rate <= 40 or heart_rate >= 131) else 2 if (111 <= heart_rate <= 130) else 1 if ((41 <= heart_rate <= 50) or (91 <= heart_rate <= 110)) else 0,
            'consciousness_score': 3 if consciousness != 'Alert' else 0,
        }


class VitalSignAlert(BaseModel):
    """Clinical alerts generated from vital signs / early warning scores."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vital_sign_alerts')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='vital_sign_alerts')
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, related_name='vital_sign_alerts',
                             null=True, blank=True)
    vital_sign = models.ForeignKey(VitalSign, on_delete=models.CASCADE, related_name='alerts')
    early_warning_score = models.ForeignKey(EarlyWarningScore, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='alerts')
    
    alert_type = models.CharField(max_length=50, choices=[
        ('early_warning', 'Early Warning Score'),
        ('bp_abnormal', 'Blood Pressure Abnormal'),
        ('fever', 'Fever / Temperature Abnormal'),
        ('tachycardia', 'Heart Rate Abnormal'),
        ('bradycardia', 'Heart Rate Abnormal'),
        ('tachypnoea', 'Respiratory Rate Abnormal'),
        ('hypoxia', 'Oxygen Saturation Low'),
        ('critical', 'Critical Alert'),
        ('custom', 'Custom Alert')
    ])
    severity = models.CharField(max_length=20, choices=[
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')
    ], default='medium')
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='acknowledged_vital_alerts')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='resolved_vital_alerts')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    notification_sent = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = _('Vital Sign Alert')
        verbose_name_plural = _('Vital Sign Alerts')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.patient.get_full_name()}"
