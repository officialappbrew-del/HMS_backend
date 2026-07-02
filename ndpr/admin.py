from django.contrib import admin
from .models import ConsentRecord, DataSubjectRequest, DataBreach, NDPRAuditLog, ComplianceReport


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ['patient_name', 'patient_id', 'consent_type', 'status', 'expiry_date', 'consent_method', 'created_at']
    list_filter = ['tenant', 'consent_type', 'status', 'consent_method', 'created_at']
    search_fields = ['patient_name', 'patient_id', 'purpose']
    readonly_fields = ['created_at', 'updated_at', 'is_active']


@admin.register(DataSubjectRequest)
class DataSubjectRequestAdmin(admin.ModelAdmin):
    list_display = ['requester_name', 'request_type', 'status', 'urgency', 'submitted_at', 'completed_at']
    list_filter = ['tenant', 'request_type', 'status', 'urgency', 'submitted_at']
    search_fields = ['requester_name', 'requester_contact', 'reason', 'response']
    readonly_fields = ['created_at', 'updated_at', 'is_active', 'submitted_at', 'processed_at', 'completed_at']


@admin.register(DataBreach)
class DataBreachAdmin(admin.ModelAdmin):
    list_display = ['breach_type', 'severity', 'status', 'affected_individuals', 'reported_to_nitda', 'breach_date', 'response_time_hours']
    list_filter = ['tenant', 'breach_type', 'severity', 'status', 'reported_to_nitda', 'breach_date']
    search_fields = ['description', 'containment_actions', 'investigation_findings']
    readonly_fields = ['created_at', 'updated_at', 'is_active', 'notifications_sent_count', 'response_time_hours']


@admin.register(NDPRAuditLog)
class NDPRAuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'resource_type', 'resource_id', 'patient_id', 'created_at']
    list_filter = ['tenant', 'action', 'created_at']
    search_fields = ['description', 'resource_id', 'patient_id', 'ip_address']
    readonly_fields = ['created_at', 'updated_at', 'is_active']


@admin.register(ComplianceReport)
class ComplianceReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'status', 'period_start', 'period_end', 'generated_by', 'created_at']
    list_filter = ['tenant', 'report_type', 'status', 'period_end']
    search_fields = ['title', 'summary']
    readonly_fields = ['created_at', 'updated_at', 'is_active']
