from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import BaseModel
from patients.models import Patient
from tenants.models import Tenant, TenantUser


class Conversation(BaseModel):
    class Kind(models.TextChoices):
        PATIENT = 'patient', 'Patient support'
        STAFF = 'staff', 'Staff chat'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        PENDING = 'pending', 'Pending'
        CLOSED = 'closed', 'Closed'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='messaging_conversations')
    kind = models.CharField(max_length=16, choices=Kind.choices)
    subject = models.CharField(max_length=180)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)
    patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.CASCADE, related_name='conversations')
    assigned_to = models.ForeignKey(TenantUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_conversations')
    opened_by_patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.SET_NULL, related_name='opened_conversations')
    opened_by_staff = models.ForeignKey(TenantUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='opened_conversations')
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'kind', 'status', 'last_message_at'], name='messaging_conv_tenant_kind_idx'),
            models.Index(fields=['tenant', 'assigned_to', 'status'], name='messaging_conv_assignee_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(kind='patient', patient__isnull=False, opened_by_patient__isnull=False, opened_by_staff__isnull=True)
                    | Q(kind='staff', patient__isnull=True, opened_by_patient__isnull=True, opened_by_staff__isnull=False)
                ),
                name='messaging_conversation_kind_subject',
            ),
        ]

    def __str__(self):
        return self.subject


class ConversationParticipant(BaseModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    tenant_user = models.ForeignKey(TenantUser, null=True, blank=True, on_delete=models.CASCADE, related_name='message_participations')
    patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.CASCADE, related_name='message_participations')
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(Q(tenant_user__isnull=False, patient__isnull=True) | Q(tenant_user__isnull=True, patient__isnull=False)),
                name='messaging_participant_one_identity',
            ),
            models.UniqueConstraint(fields=['conversation', 'tenant_user'], condition=Q(tenant_user__isnull=False), name='messaging_unique_staff_participant'),
            models.UniqueConstraint(fields=['conversation', 'patient'], condition=Q(patient__isnull=False), name='messaging_unique_patient_participant'),
        ]


class Message(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='messaging_messages')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender_staff = models.ForeignKey(TenantUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='sent_messages')
    sender_patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.SET_NULL, related_name='sent_messages')
    body = models.TextField(max_length=5000)
    is_internal_note = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['conversation', 'created_at'], name='messaging_msg_conv_created_idx')]
        constraints = [
            models.CheckConstraint(
                check=(Q(sender_staff__isnull=False, sender_patient__isnull=True) | Q(sender_staff__isnull=True, sender_patient__isnull=False)),
                name='messaging_message_one_sender',
            ),
        ]


class MessagingNotification(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='messaging_notifications')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='message_notifications')
    recipient_staff = models.ForeignKey(TenantUser, null=True, blank=True, on_delete=models.CASCADE, related_name='message_notifications')
    recipient_patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.CASCADE, related_name='message_notifications')
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=200)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient_staff', 'read_at', 'created_at'], name='messaging_notice_staff_idx'),
            models.Index(fields=['recipient_patient', 'read_at', 'created_at'], name='messaging_notice_patient_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(Q(recipient_staff__isnull=False, recipient_patient__isnull=True) | Q(recipient_staff__isnull=True, recipient_patient__isnull=False)),
                name='messaging_notification_one_recipient',
            ),
        ]

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at', 'updated_at'])