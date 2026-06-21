from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from .models import (
    GlobalUser, User2FA, RSAKey, UserSession,
    SecurityEvent, UserNotification
)


class User2FAInline(admin.StackedInline):
    model = User2FA
    can_delete = False
    verbose_name_plural = 'Two-Factor Authentication'
    fields = ('method', 'is_enabled', 'require_2fa_for_login',
              'allow_remember_device', 'failed_attempts', 'last_used')
    readonly_fields = ('failed_attempts', 'last_used')


class RSAKeyInline(admin.TabularInline):
    model = RSAKey
    extra = 0
    fields = ('key_name', 'key_fingerprint', 'expires_at',
              'is_primary', 'is_active', 'last_used')
    readonly_fields = ('key_fingerprint', 'last_used')


@admin.register(GlobalUser)
class GlobalUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name',
                    'role', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'employee_id')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal Info'), {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        (_('Employment'), {'fields': ('employee_id', 'role')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Global Permissions'), {
            'fields': ('can_create_tenants', 'can_suspend_tenants',
                      'can_delete_tenants', 'can_view_all_tenants'),
        }),
        (_('Security'), {
            'fields': ('two_fa_enabled', 'two_fa_method', 'rsa_public_key',
                      'login_attempts', 'account_locked_until'),
        }),
        (_('Important Dates'), {'fields': ('last_login', 'date_joined', 'password_changed_at')}),
        (_('Metadata'), {'fields': ('created_by', 'notes')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2',
                      'first_name', 'last_name', 'role', 'is_staff', 'is_superuser'),
        }),
    )
    
    readonly_fields = ('last_login', 'date_joined', 'password_changed_at',
                      'login_attempts', 'account_locked_until')
    
    inlines = [User2FAInline, RSAKeyInline]
    
    actions = ['lock_accounts', 'unlock_accounts', 'force_password_reset']
    
    def lock_accounts(self, request, queryset):
        updated = queryset.update(account_locked_until=None)
        self.message_user(
            request,
            f'{updated} account(s) locked.',
            messages.SUCCESS
        )
    lock_accounts.short_description = "Lock selected accounts"
    
    def unlock_accounts(self, request, queryset):
        updated = queryset.update(account_locked_until=None, login_attempts=0)
        self.message_user(
            request,
            f'{updated} account(s) unlocked.',
            messages.SUCCESS
        )
    unlock_accounts.short_description = "Unlock selected accounts"
    
    def force_password_reset(self, request, queryset):
        for user in queryset:
            user.set_unusable_password()
            user.save()
        self.message_user(
            request,
            f'{queryset.count()} user(s) forced to reset password.',
            messages.SUCCESS
        )
    force_password_reset.short_description = "Force password reset for selected users"


@admin.register(User2FA)
class User2FAAdmin(admin.ModelAdmin):
    list_display = ('user', 'method', 'is_enabled', 'last_used', 'failed_attempts')
    list_filter = ('method', 'is_enabled', 'require_2fa_for_login')
    search_fields = ('user__username', 'user__email', 'sms_phone', 'backup_email')
    readonly_fields = ('last_used', 'failed_attempts', 'last_failed_attempt',
                      'backup_codes_generated_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'method', 'is_enabled')}),
        (_('Verification Methods'), {
            'fields': ('totp_secret', 'totp_verified',
                      'sms_phone', 'sms_verified',
                      'backup_email', 'email_verified'),
        }),
        (_('Backup Codes'), {
            'fields': ('backup_codes', 'backup_codes_generated_at'),
        }),
        (_('Security Settings'), {
            'fields': ('require_2fa_for_login', 'allow_remember_device', 'trusted_devices'),
        }),
        (_('Usage Tracking'), {
            'fields': ('last_used', 'failed_attempts', 'last_failed_attempt'),
        }),
    )


@admin.register(RSAKey)
class RSAKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'key_name', 'key_fingerprint_short',
                    'expires_at', 'is_primary', 'is_active', 'last_used')
    list_filter = ('is_primary', 'is_active', 'algorithm', 'expires_at')
    search_fields = ('user__username', 'key_name', 'key_fingerprint')
    readonly_fields = ('key_fingerprint', 'created_at', 'last_used',
                      'usage_count', 'expires_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'key_name', 'is_primary', 'is_active')}),
        (_('Key Information'), {
            'fields': ('public_key', 'private_key_encrypted',
                      'key_fingerprint', 'key_size', 'algorithm'),
        }),
        (_('Usage'), {
            'fields': ('key_usage', 'last_used', 'usage_count'),
        }),
        (_('Dates'), {
            'fields': ('created_at', 'expires_at'),
        }),
    )
    
    def key_fingerprint_short(self, obj):
        return obj.key_fingerprint[:16] + '...' if obj.key_fingerprint else ''
    key_fingerprint_short.short_description = 'Fingerprint'


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session_key_short', 'ip_address',
                    'last_activity', 'expires_at', 'is_active')
    list_filter = ('is_active', 'requires_reauth', 'is_trusted_device', 'last_activity')
    search_fields = ('user__username', 'ip_address', 'session_key')
    readonly_fields = ('session_key', 'created_at', 'last_activity')
    
    fieldsets = (
        (None, {'fields': ('user', 'session_key', 'ip_address')}),
        (_('Device Information'), {
            'fields': ('user_agent', 'device_info', 'location_info'),
        }),
        (_('Session State'), {
            'fields': ('is_active', 'last_activity', 'expires_at'),
        }),
        (_('Security'), {
            'fields': ('requires_reauth', 'is_trusted_device'),
        }),
    )
    
    def session_key_short(self, obj):
        return obj.session_key[:20] + '...' if obj.session_key else ''
    session_key_short.short_description = 'Session Key'
    
    def has_add_permission(self, request):
        return False


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'user', 'severity', 'created_at',
                    'ip_address', 'resolved')
    list_filter = ('event_type', 'severity', 'resolved', 'created_at')
    search_fields = ('user__username', 'ip_address', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'event_type', 'severity', 'description')}),
        (_('Technical Details'), {
            'fields': ('ip_address', 'user_agent', 'metadata'),
        }),
        (_('Resolution'), {
            'fields': ('resolved', 'resolved_at', 'resolved_by', 'resolution_notes'),
        }),
    )
    
    actions = ['mark_as_resolved', 'mark_as_unresolved']
    
    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(
            resolved=True,
            resolved_at=timezone.now(),
            resolved_by=request.user
        )
        self.message_user(
            request,
            f'{updated} event(s) marked as resolved.',
            messages.SUCCESS
        )
    mark_as_resolved.short_description = "Mark selected events as resolved"
    
    def mark_as_unresolved(self, request, queryset):
        updated = queryset.update(
            resolved=False,
            resolved_at=None,
            resolved_by=None
        )
        self.message_user(
            request,
            f'{updated} event(s) marked as unresolved.',
            messages.SUCCESS
        )
    mark_as_unresolved.short_description = "Mark selected events as unresolved"


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'priority',
                    'is_read', 'created_at')
    list_filter = ('notification_type', 'priority', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at', 'updated_at', 'read_at',
                      'action_taken_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'notification_type', 'priority',
                          'title', 'message', 'data')}),
        (_('Delivery'), {
            'fields': ('sent_via_email', 'sent_via_sms',
                      'sent_via_push', 'sent_via_system'),
        }),
        (_('Status'), {
            'fields': ('is_read', 'read_at', 'action_taken',
                      'action_taken_at', 'action_notes'),
        }),
        (_('Expiry'), {
            'fields': ('expires_at',),
        }),
    )
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(
            request,
            f'{updated} notification(s) marked as read.',
            messages.SUCCESS
        )
    mark_as_read.short_description = "Mark selected notifications as read"
    
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False, read_at=None)
        self.message_user(
            request,
            f'{updated} notification(s) marked as unread.',
            messages.SUCCESS
        )
    mark_as_unread.short_description = "Mark selected notifications as unread"