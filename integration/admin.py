from django.contrib import admin

from .models import IntegrationClient, IntegrationMessage


@admin.register(IntegrationClient)
class IntegrationClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'is_active', 'api_key_prefix', 'last_used')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'description')


@admin.register(IntegrationMessage)
class IntegrationMessageAdmin(admin.ModelAdmin):
    list_display = ('protocol', 'direction', 'message_type', 'status', 'source_system', 'tenant', 'created_at')
    list_filter = ('protocol', 'direction', 'status', 'message_type', 'tenant')
    search_fields = ('source_system', 'destination_system', 'correlation_id')
    readonly_fields = ('created_at', 'updated_at')
