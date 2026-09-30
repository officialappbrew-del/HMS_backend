from django.contrib import admin

from .models import Conversation, ConversationParticipant, Message, MessagingNotification


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'kind', 'subject', 'status', 'assigned_to', 'last_message_at')
    list_filter = ('tenant', 'kind', 'status', 'priority')
    search_fields = ('subject', 'patient__first_name', 'patient__last_name')


admin.site.register(ConversationParticipant)
admin.site.register(Message)
admin.site.register(MessagingNotification)