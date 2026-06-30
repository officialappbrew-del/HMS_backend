from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from tenants.models import Tenant
from patients.models import Patient


class DrugInteraction(BaseModel):
    """Drug-drug interaction database."""
    class Severity(models.TextChoices):
        MAJOR = 'major', _('Major')
        MODERATE = 'moderate', _('Moderate')
        MINOR = 'minor', _('Minor')
        CONTRAINDICATED = 'contraindicated', _('Contraindicated')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='drug_interactions')
    drug1 = models.CharField(max_length=200)
    drug2 = models.CharField(max_length=200)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MODERATE)
    description = models.TextField()
    mechanism = models.TextField(blank=True)
    clinical_effect = models.TextField(blank=True)
    management = models.TextField(blank=True)
    alternative_drugs = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    last_reviewed = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Drug Interaction')
        verbose_name_plural = _('Drug Interactions')
        unique_together = ['tenant', 'drug1', 'drug2']
        ordering = ['-severity', 'drug1']

    def __str__(self):
        return f"{self.drug1} + {self.drug2} ({self.severity})"


class AllergyCheck(BaseModel):
    """Patient allergy checks and cross-reactivity."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='allergy_checks')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='allergy_checks')
    allergen = models.CharField(max_length=200)
    allergy_type = models.CharField(max_length=50, choices=[
        ('drug', 'Drug'),
        ('food', 'Food'),
        ('environmental', 'Environmental'),
        ('latex', 'Latex'),
        ('other', 'Other')
    ])
    reaction = models.TextField()
    severity = models.CharField(max_length=20, choices=[
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('severe', 'Severe'),
        ('life_threatening', 'Life-threatening')
    ], default='moderate')
    cross_reactivity = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Allergy Check')
        verbose_name_plural = _('Allergy Checks')
        ordering = ['-severity', '-created_at']

    def __str__(self):
        return f"{self.allergen} - {self.patient.get_full_name()}"


class DosingGuideline(BaseModel):
    """Drug dosing guidelines and calculations."""
    class DrugCategory(models.TextChoices):
        ANTIMALARIAL = 'antimalarial', _('Antimalarial')
        ANTIBIOTIC = 'antibiotic', _('Antibiotic')
        ANALGESIC = 'analgesic', _('Analgesic')
        ANTIHYPERTENSIVE = 'antihypertensive', _('Antihypertensive')
        ANTIDIABETIC = 'antidiabetic', _('Antidiabetic')
        ANTIPARASITIC = 'antiparasitic', _('Antiparasitic')
        VITAMIN = 'vitamin', _('Vitamin')
        OTHER = 'other', _('Other')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='dosing_guidelines')
    drug_name = models.CharField(max_length=200)
    drug_category = models.CharField(max_length=30, choices=DrugCategory.choices, default=DrugCategory.OTHER)
    standard_dose = models.CharField(max_length=100)
    pediatric_dose = models.CharField(max_length=100, blank=True)
    renal_adjustment = models.TextField(blank=True)
    hepatic_adjustment = models.TextField(blank=True)
    max_daily_dose = models.CharField(max_length=100, blank=True)
    route = models.CharField(max_length=50, choices=[
        ('oral', 'Oral'),
        ('iv', 'IV'),
        ('im', 'IM'),
        ('sc', 'SC'),
        ('topical', 'Topical'),
        ('inhalation', 'Inhalation')
    ], default='oral')
    frequency = models.CharField(max_length=100)
    duration_guidelines = models.TextField(blank=True)
    special_considerations = models.TextField(blank=True)
    evidence_level = models.CharField(max_length=20, choices=[
        ('A', 'Level A - Strong evidence'),
        ('B', 'Level B - Moderate evidence'),
        ('C', 'Level C - Limited evidence'),
        ('D', 'Level D - Expert opinion')
    ], default='C')
    source = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('Dosing Guideline')
        verbose_name_plural = _('Dosing Guidelines')
        ordering = ['drug_category', 'drug_name']

    def __str__(self):
        return f"{self.drug_name} ({self.get_drug_category_display()})"


class ClinicalGuideline(BaseModel):
    """Clinical practice guidelines."""
    class Category(models.TextChoices):
        INFECTIOUS_DISEASE = 'infectious_disease', _('Infectious Diseases')
        CARDIOVASCULAR = 'cardiovascular', _('Cardiovascular')
        ENDOCRINOLOGY = 'endocrinology', _('Endocrinology')
        RESPIRATORY = 'respiratory', _('Respiratory')
        GASTROENTEROLOGY = 'gastroenterology', _('Gastroenterology')
        NEUROLOGY = 'neurology', _('Neurology')
        PEDIATRICS = 'pediatrics', _('Pediatrics')
        OBSTETRICS = 'obstetrics', _('Obstetrics & Gynecology')
        SURGERY = 'surgery', _('Surgery')
        EMERGENCY = 'emergency', _('Emergency Medicine')
        NCD = 'ncd', _('Non-Communicable Diseases')
        OTHER = 'other', _('Other')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='clinical_guidelines')
    title = models.CharField(max_length=300)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    description = models.TextField()
    recommendations = models.JSONField(default=list)
    contraindications = models.JSONField(default=list, blank=True)
    monitoring_requirements = models.JSONField(default=list, blank=True)
    evidence_level = models.CharField(max_length=20, choices=[
        ('A', 'Level A - Strong evidence'),
        ('B', 'Level B - Moderate evidence'),
        ('C', 'Level C - Limited evidence'),
        ('D', 'Level D - Expert opinion')
    ], default='C')
    source = models.CharField(max_length=200, blank=True)
    last_reviewed = models.DateTimeField(null=True, blank=True)
    next_review = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    tags = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _('Clinical Guideline')
        verbose_name_plural = _('Clinical Guidelines')
        ordering = ['category', 'title']
        indexes = [
            models.Index(fields=['tenant', 'category', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class RiskAssessment(BaseModel):
    """Risk calculation records for patients."""
    class RiskType(models.TextChoices):
        CARDIOVASCULAR = 'cardiovascular', _('Cardiovascular Risk')
        DIABETES = 'diabetes', _('Diabetes Risk')
        PREGNANCY = 'pregnancy', _('Pregnancy Risk')
        FALL = 'fall', _('Fall Risk')
        PRESSURE_ULCER = 'pressure_ulcer', _('Pressure Ulcer Risk')
        SEPSIS = 'sepsis', _('Sepsis Risk')
        DVT = 'dvt', _('DVT Risk')
        OTHER = 'other', _('Other')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='risk_assessments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='risk_assessments')
    risk_type = models.CharField(max_length=30, choices=RiskType.choices)
    score = models.FloatField()
    risk_percentage = models.FloatField()
    risk_category = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
        ('critical', 'Critical')
    ])
    input_data = models.JSONField()
    recommendations = models.JSONField(default=list)
    calculated_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True,
                                     limit_choices_to={'role__in': ['doctor', 'nurse']})
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Risk Assessment')
        verbose_name_plural = _('Risk Assessments')
        ordering = ['-calculated_at']

    def __str__(self):
        return f"{self.get_risk_type_display()} - {self.patient.get_full_name()} ({self.risk_category})"


class PatientAlert(BaseModel):
    """Patient-specific clinical alerts and notifications."""
    class AlertType(models.TextChoices):
        DRUG_INTERACTION = 'drug_interaction', _('Drug Interaction')
        ALLERGY = 'allergy', _('Allergy Warning')
        DOSING = 'dosing', _('Dosing Alert')
        LAB_RESULT = 'lab_result', _('Lab Result Alert')
        VITAL_SIGN = 'vital_sign', _('Vital Sign Alert')
        RISK_ASSESSMENT = 'risk_assessment', _('Risk Assessment')
        GUIDELINE = 'guideline', _('Guideline Reminder')
        CUSTOM = 'custom', _('Custom Alert')

    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        CRITICAL = 'critical', _('Critical')

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='patient_alerts')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='patient_alerts')
    alert_type = models.CharField(max_length=30, choices=AlertType.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    title = models.CharField(max_length=200)
    message = models.TextField()
    recommendation = models.TextField(blank=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='acknowledged_cds_alerts')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    dismissed = models.BooleanField(default=False)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    related_object_id = models.CharField(max_length=50, blank=True)
    related_object_type = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = _('Patient Alert')
        verbose_name_plural = _('Patient Alerts')
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'patient', 'acknowledged', 'dismissed']),
        ]

    def __str__(self):
        return f"{self.title} - {self.patient.get_full_name()}"
