from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    Tenant, SubscriptionPlan, TenantUser, Department,
    TenantSetting, TenantModule, TenantInvitation,
    TenantActivityLog, TenantBackup, BulkTenantUserUpload,
    CommunicationProfile
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price_monthly', 'max_users',
                    'max_patients', 'is_default', 'is_active')
    list_filter = ('is_default', 'is_active', 'currency')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('name', 'code', 'description', 'is_default', 'is_active')}),
        (_('Pricing'), {
            'fields': ('price_monthly', 'price_quarterly', 'price_yearly', 'currency'),
        }),
        (_('Limits'), {
            'fields': ('max_users', 'max_patients', 'max_storage_gb', 'max_api_calls_per_day'),
        }),
        (_('Features'), {
            'fields': ('features', 'modules'),
        }),
        (_('Trial'), {
            'fields': ('trial_period_days', 'is_trial_available'),
        }),
        (_('Display'), {
            'fields': ('display_order',),
        }),
    )
    
    actions = ['set_as_default', 'activate_plans', 'deactivate_plans']
    
    def set_as_default(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                'Please select only one plan to set as default.',
                messages.WARNING
            )
            return
        
        plan = queryset.first()
        # Remove default from other plans
        SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)
        
        # Set this plan as default
        plan.is_default = True
        plan.save()
        
        self.message_user(
            request,
            f'{plan.name} set as default plan.',
            messages.SUCCESS
        )
    set_as_default.short_description = "Set selected as default"
    
    def activate_plans(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'{updated} plan(s) activated.',
            messages.SUCCESS
        )
    activate_plans.short_description = "Activate selected plans"
    
    def deactivate_plans(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f'{updated} plan(s) deactivated.',
            messages.SUCCESS
        )
    deactivate_plans.short_description = "Deactivate selected plans"


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'domain', 'subscription_status',
                    'nhis_accreditation', 'created_at')
    list_filter = ('subscription_status', 'nhis_accreditation',
                   'facility_type', 'state', 'created_at')
    search_fields = ('name', 'code', 'domain', 'email', 'registration_number')
    readonly_fields = ('created_at', 'updated_at', 'code', 'schema_name')
    
    fieldsets = (
        (None, {'fields': ('name', 'code', 'domain', 'schema_name')}),
        (_('Contact Information'), {
            'fields': ('email', 'phone', 'phone2', 'address', 'city',
                      'state', 'lga', 'country', 'website'),
        }),
        (_('Facility Details'), {
            'fields': ('facility_type', 'registration_number', 'tax_id',
                      'bed_capacity', 'established_date', 'emergency_services'),
        }),
        (_('Subscription'), {
            'fields': ('subscription_plan', 'subscription_status',
                      'subscription_start_date', 'subscription_end_date',
                      'monthly_fee', 'payment_method', 'billing_email'),
        }),
        (_('NHIS Integration'), {
            'fields': ('nhis_accreditation', 'nhis_provider_id',
                      'nhis_accreditation_date', 'nhis_expiry_date'),
        }),
        (_('Configuration'), {
            'fields': ('config', 'features', 'operating_hours'),
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'notes', 'logo'),
        }),
        (_('Dates'), {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    
    actions = ['activate_tenants', 'suspend_tenants', 'cancel_subscriptions']
    
    def activate_tenants(self, request, queryset):
        updated = queryset.update(
            subscription_status=Tenant.SubscriptionStatus.ACTIVE
        )
        self.message_user(
            request,
            f'{updated} tenant(s) activated.',
            messages.SUCCESS
        )
    activate_tenants.short_description = "Activate selected tenants"
    
    def suspend_tenants(self, request, queryset):
        updated = queryset.update(
            subscription_status=Tenant.SubscriptionStatus.SUSPENDED
        )
        self.message_user(
            request,
            f'{updated} tenant(s) suspended.',
            messages.SUCCESS
        )
    suspend_tenants.short_description = "Suspend selected tenants"
    
    def cancel_subscriptions(self, request, queryset):
        updated = queryset.update(
            subscription_status=Tenant.SubscriptionStatus.CANCELLED
        )
        self.message_user(
            request,
            f'{updated} tenant subscription(s) cancelled.',
            messages.SUCCESS
        )
    cancel_subscriptions.short_description = "Cancel selected subscriptions"


@admin.register(CommunicationProfile)
class CommunicationProfileAdmin(admin.ModelAdmin):
    list_display = ('tenant_name', 'email_from', 'from_name', 'sms_provider', 'sms_sender_id', 'email_enabled', 'sms_enabled')
    list_filter = ('email_provider', 'sms_provider', 'email_enabled', 'sms_enabled', 'consent_tracking_enabled', 'dnd_enabled')
    search_fields = ('tenant__name', 'tenant__code', 'email_from', 'from_name', 'sms_sender_id', 'sms_phone_number')
    readonly_fields = ('created_at', 'updated_at', 'tenant')
    fieldsets = (
        (None, {'fields': ('tenant',)}),
        (_('Email Identity'), {
            'fields': ('email_from', 'from_name', 'reply_to', 'verified_domain', 'email_provider'),
        }),
        (_('Email Provider Credentials'), {
            'fields': ('email_username', 'email_password', 'email_host', 'email_port', 'email_use_tls'),
        }),
        (_('SMS Identity'), {
            'fields': ('sms_provider', 'sms_sender_id', 'sms_phone_number', 'sms_country_code'),
        }),
        (_('SMS Provider Credentials'), {
            'fields': ('sms_api_key',),
        }),
        (_('Compliance'), {
            'fields': ('consent_tracking_enabled', 'opt_out_message', 'dnd_enabled', 'message_templates'),
        }),
        (_('Channels & Limits'), {
            'fields': ('email_enabled', 'sms_enabled', 'daily_email_limit', 'daily_sms_limit'),
        }),
        (_('Dates'), {'fields': ('created_at', 'updated_at')}),
    )
    
    def tenant_name(self, obj):
        return obj.tenant.name
    tenant_name.short_description = 'Tenant'
    tenant_name.admin_order_field = 'tenant__name'

