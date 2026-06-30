from django.db import models
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient, PatientVisit


class MedicalRecord(BaseModel):
    """Main patient medical record."""
    class RecordType(models.TextChoices):
        OUTPATIENT = 'outpatient', _('Outpatient')
        INPATIENT = 'inpatient', _('Inpatient')
        EMERGENCY = 'emergency', _('Emergency')
        DAY_CARE = 'day_care', _('Day Care')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='medical_records')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_records')
    visit = models.ForeignKey(PatientVisit, on_delete=models.SET_NULL, null=True, blank=True, related_name='medical_records')
    
    record_number = models.CharField(max_length=50, unique=True, blank=True)
    record_type = models.CharField(max_length=20, choices=RecordType.choices, default=RecordType.OUTPATIENT)
    
    primary_doctor = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                      limit_choices_to={'role': 'doctor'}, related_name='primary_records')
    
    chief_complaint = models.TextField(blank=True)
    history_of_present_illness = models.TextField(blank=True)
    past_medical_history = models.TextField(blank=True)
    family_history = models.TextField(blank=True)
    social_history = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='closed_records')
    
    class Meta:
        verbose_name = _('Medical Record')
        verbose_name_plural = _('Medical Records')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'patient', '-created_at']),
            models.Index(fields=['record_number']),
        ]
    
    def __str__(self):
        return f"EMR {self.record_number} - {self.patient.get_full_name()}"
    
    def save(self, *args, **kwargs):
        if not self.record_number:
            self.record_number = self.generate_record_number()
        super().save(*args, **kwargs)
    
    def generate_record_number(self):
        from django.utils import timezone
        date_str = (self.created_at or timezone.now()).strftime('%Y%m%d')
        return f"EMR-{date_str}-{self.pk or 'ID'}"


class ProgressNote(BaseModel):
    """Clinical progress notes (SOAP format)."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='progress_notes')
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='progress_notes')
    visit = models.ForeignKey(PatientVisit, on_delete=models.SET_NULL, null=True, blank=True, related_name='progress_notes')
    
    author = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                              limit_choices_to={'role__in': ['doctor', 'nurse']})
    
    subjective = models.TextField(blank=True)
    objective = models.TextField(blank=True)
    assessment = models.TextField(blank=True)
    plan = models.TextField(blank=True)
    
    note_type = models.CharField(max_length=20, choices=[
        ('progress', 'Progress Note'),
        ('consultation', 'Consultation Note'),
        ('procedure', 'Procedure Note'),
        ('discharge', 'Discharge Summary'),
        ('transfer', 'Transfer Note'),
        ('admission', 'Admission Note'),
        ('nursing', 'Nursing Note'),
    ], default='progress')
    
    is_signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('Progress Note')
        verbose_name_plural = _('Progress Notes')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['medical_record', '-created_at']),
        ]
    
    def __str__(self):
        return f"Note {self.pk} - {self.medical_record.record_number}"


class ClinicalDocument(BaseModel):
    """Uploaded clinical documents and images."""
    class DocumentType(models.TextChoices):
        LAB_RESULT = 'lab_result', _('Lab Result')
        RADIOLOGY = 'radiology', _('Radiology Report')
        PRESCRIPTION = 'prescription', _('Prescription')
        CONSENT = 'consent', _('Consent Form')
        IMAGING = 'imaging', _('Medical Imaging')
        PHOTO = 'photo', _('Clinical Photo')
        REFERRAL = 'referral', _('Referral Letter')
        DISCHARGE = 'discharge', _('Discharge Summary')
        OTHER = 'other', _('Other')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='clinical_documents')
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='documents')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='clinical_documents')
    
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    file = models.FileField(upload_to='clinical_documents/%Y/%m/%d/', null=True, blank=True)
    file_url = models.URLField(blank=True)
    mime_type = models.CharField(max_length=50, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    
    uploaded_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name = _('Clinical Document')
        verbose_name_plural = _('Clinical Documents')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['medical_record', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.patient.get_full_name()}"


class ProblemList(BaseModel):
    """Patient problem list (active and resolved problems)."""
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        RESOLVED = 'resolved', _('Resolved')
        CHRONIC = 'chronic', _('Chronic')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='problem_list')
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='problems')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='problem_list')
    
    problem = models.CharField(max_length=200)
    icd10_code = models.CharField(max_length=20, blank=True)
    onset_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    diagnosed_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    limit_choices_to={'role': 'doctor'})
    notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = _('Problem List Entry')
        verbose_name_plural = _('Problem List')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['medical_record', 'status']),
        ]
    
    def __str__(self):
        return f"{self.problem} ({self.get_status_display()})"


class Allergy(BaseModel):
    """Patient allergy records."""
    class Severity(models.TextChoices):
        MILD = 'mild', _('Mild')
        MODERATE = 'moderate', _('Moderate')
        SEVERE = 'severe', _('Severe')
    
    class AllergyType(models.TextChoices):
        DRUG = 'drug', _('Drug')
        FOOD = 'food', _('Food')
        ENVIRONMENTAL = 'environmental', _('Environmental')
        LATEX = 'latex', _('Latex')
        OTHER = 'other', _('Other')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='allergies')
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='allergies')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='emr_allergies')
    
    allergen = models.CharField(max_length=200)
    allergy_type = models.CharField(max_length=20, choices=AllergyType.choices)
    reaction = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MODERATE)
    
    first_identified = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   limit_choices_to={'role': 'doctor'})
    
    class Meta:
        verbose_name = _('Allergy')
        verbose_name_plural = _('Allergies')
        ordering = ['-severity', '-created_at']
        indexes = [
            models.Index(fields=['medical_record', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.allergen} ({self.get_severity_display()}) - {self.patient.get_full_name()}"
