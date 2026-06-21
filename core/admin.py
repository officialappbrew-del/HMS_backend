from django.contrib import admin
from .models import (
    Country, State, LGA, FacilityType, Specialization,
    Language, NotificationTemplate, SystemSetting, AuditLog, BackupLog
)

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'phone_code', 'currency')
    search_fields = ('name', 'code')
    list_filter = ('currency',)


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'country')
    search_fields = ('name', 'code')
    list_filter = ('country',)


@admin.register(LGA)
class LGAAdmin(admin.ModelAdmin):
    list_display = ('name', 'state')
    search_fields = ('name', 'state__name')
    list_filter = ('state',)


@admin.register(FacilityType)
class FacilityTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'notification_type', 'language', 'subject')
    list_filter = ('notification_type', 'language')
    search_fields = ('name', 'subject', 'body')


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'category', 'data_type')
    list_filter = ('category', 'data_type')
    search_fields = ('key', 'description')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'resource_type', 'user', 'timestamp')
    list_filter = ('action', 'resource_type', 'timestamp')
    search_fields = ('user__username', 'resource_id', 'ip_address')
    readonly_fields = ('timestamp', 'ip_address', 'user_agent')
    date_hierarchy = 'timestamp'


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('backup_type', 'status', 'start_time', 'end_time', 'duration')
    list_filter = ('backup_type', 'status', 'start_time')
    readonly_fields = ('start_time', 'end_time', 'duration')
    date_hierarchy = 'start_time'