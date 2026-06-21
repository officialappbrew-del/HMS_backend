from django.contrib import admin
from django.contrib import messages
from django.utils import timezone

from .models import (
    Patient, PatientVisit, PatientDocument,
    PatientAllergy, PatientMedication, Appointment
)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('hospital_number', 'get_full_name', 'gender', 'age',
                    'phone', 'patient_status', 'last_visit')
    list_filter = ('patient_status', 'gender', 'marital_status',
                   'blood_group', 'registration_date')
    search_fields = ('hospital_number', 'nhis_number', 'first_name',
                     'last_name', 'phone', 'email')
    readonly_fields = ('hospital_number', 'age', 'registration_date')
    
    fieldsets = (
        (None, {'fields': ('tenant', 'hospital_number', 'nhis_number', 'nin')}),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'middle_name',
                      'date_of_birth', 'age', 'gender', 'marital_status'),
        }),
        ('Contact Information', {
            'fields': ('phone', 'phone2', 'email', 'address',
                      'city', 'state', 'lga', 'country'),
        }),
        ('Next of Kin', {
            'fields': ('next_of_kin_name', 'next_of_kin_relationship',
                      'next_of_kin_phone', 'next_of_kin_address'),
        }),
        ('Medical Information', {
            'fields': ('blood_group', 'genotype', 'known_allergies',
                      'chronic_conditions', 'current_medications',
                      'surgical_history', 'family_history'),
        }),
        ('Insurance', {
            'fields': ('has_insurance', 'insurance_company',
                      'insurance_policy_number', 'insurance_expiry'),
        }),
        ('Additional Information', {
            'fields': ('occupation', 'religion', 'ethnicity',
                      'language_spoken', 'photo', 'notes'),
        }),
        ('Status', {
            'fields': ('patient_status', 'last_visit'),
        }),
        ('Metadata', {
            'fields': ('registered_by', 'registration_date'),
        }),
    )


@admin.register(PatientVisit)
class PatientVisitAdmin(admin.ModelAdmin):
    list_display = ('visit_number', 'patient', 'visit_type',
                    'visit_status', 'checkin_time', 'triage_category')
    list_filter = ('visit_type', 'visit_status', 'triage_category',
                   'checkin_time')
    search_fields = ('visit_number', 'patient__first_name',
                     'patient__last_name', 'patient__hospital_number')
    readonly_fields = ('visit_number', 'checkin_time')
    
    fieldsets = (
        (None, {'fields': ('tenant', 'patient', 'visit_number', 'visit_type')}),
        ('Clinical Information', {
            'fields': ('chief_complaint', 'history_of_present_illness',
                      'vital_signs', 'triage_category'),
        }),
        ('Service Details', {
            'fields': ('department', 'doctor', 'nurse'),
        }),
        ('Status', {
            'fields': ('visit_status',),
        }),
        ('Timing', {
            'fields': ('checkin_time', 'triage_time', 'consultation_start_time',
                      'consultation_end_time', 'discharge_time'),
        }),
        ('Additional Information', {
            'fields': ('referral_from', 'referral_reason', 'notes'),
        }),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('appointment_number', 'patient', 'doctor',
                    'appointment_type', 'scheduled_date', 'scheduled_time',
                    'status')
    list_filter = ('appointment_type', 'status', 'scheduled_date')
    search_fields = ('appointment_number', 'patient__first_name',
                     'patient__last_name', 'doctor__first_name')
    
    fieldsets = (
        (None, {'fields': ('tenant', 'patient', 'appointment_number',
                          'appointment_type')}),
        ('Schedule', {
            'fields': ('scheduled_date', 'scheduled_time',
                      'expected_duration'),
        }),
        ('Staff Assignment', {
            'fields': ('doctor', 'department'),
        }),
        ('Status', {
            'fields': ('status',),
        }),
        ('Timing', {
            'fields': ('actual_start_time', 'actual_end_time'),
        }),
        ('Additional Information', {
            'fields': ('reason', 'notes', 'reminder_sent',
                      'reminder_sent_date'),
        }),
    )