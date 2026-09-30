from rest_framework import serializers

from tenants.models import TenantUser

from .models import Conversation, Message, MessagingNotification


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'body', 'is_internal_note', 'created_at', 'sender_name', 'sender_role', 'is_mine']
        read_only_fields = fields

    def get_sender_name(self, obj):
        sender = obj.sender_staff or obj.sender_patient
        if sender is None:
            return 'Former user'
        if obj.sender_staff:
            return f'{sender.first_name} {sender.last_name}'.strip() or sender.username or sender.email
        request = self.context.get('request')
        return 'You' if request and getattr(request.user, 'is_patient', False) else sender.get_full_name()

    def get_sender_role(self, obj):
        return obj.sender_staff.role if obj.sender_staff else 'patient'

    def get_is_mine(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        user = request.user
        if getattr(user, 'is_patient', False):
            return obj.sender_patient_id == user.pk
        staff = user if isinstance(user, TenantUser) else getattr(user, 'tenant_user', None)
        return bool(staff and obj.sender_staff_id == staff.pk)


class ConversationSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    latest_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'kind', 'subject', 'status', 'priority', 'patient', 'patient_name',
            'assigned_to', 'assigned_to_name', 'last_message_at', 'created_at',
            'latest_message', 'unread_count',
        ]
        read_only_fields = fields

    def get_patient_name(self, obj):
        return obj.patient.get_full_name() if obj.patient_id else None

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to_id:
            return None
        staff = obj.assigned_to
        return f'{staff.first_name} {staff.last_name}'.strip() or staff.username or staff.email

    def get_latest_message(self, obj):
        request = self.context.get('request')
        messages = obj.messages.all()
        if request and getattr(request.user, 'is_patient', False):
            messages = messages.filter(is_internal_note=False)
        latest = messages.order_by('-created_at', '-id').first()
        return latest.body[:160] if latest else ''

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request:
            return 0
        user = request.user
        notifications = obj.message_notifications.filter(read_at__isnull=True)
        if getattr(user, 'is_patient', False):
            return notifications.filter(recipient_patient=user).count()
        staff = user if isinstance(user, TenantUser) else getattr(user, 'tenant_user', None)
        return notifications.filter(recipient_staff=staff).count() if staff else 0


class MessagingNotificationSerializer(serializers.ModelSerializer):
    conversation_kind = serializers.CharField(source='conversation.kind', read_only=True)

    class Meta:
        model = MessagingNotification
        fields = ['id', 'conversation', 'conversation_kind', 'title', 'message', 'created_at', 'read_at']
        read_only_fields = fields