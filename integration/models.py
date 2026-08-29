import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from core.models import BaseModel
from tenants.models import Tenant


class IntegrationClient(BaseModel):
    """Partner or device credential used for HL7/FHIR exchange."""
    name = models.CharField(max_length=120, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='integration_clients', null=True, blank=True)
    description = models.TextField(blank=True)
    api_key_hash = models.CharField(max_length=255)
    api_key_prefix = models.CharField(max_length=12, default='hms_')
    is_active = models.BooleanField(default=True)
    allowed_ip_addresses = models.JSONField(default=list, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_authenticated = True

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @classmethod
    def generate_api_key(cls, name, tenant=None, description='', prefix='hms_'):
        raw_key = f"{prefix}{secrets.token_urlsafe(32)}"
        client = cls.objects.create(
            name=name,
            tenant=tenant,
            description=description,
            api_key_hash=make_password(raw_key),
            api_key_prefix=prefix,
        )
        return client, raw_key

    def verify_api_key(self, raw_key):
        return check_password(raw_key, self.api_key_hash)


class IntegrationMessage(BaseModel):
    """Immutable log of all HL7/FHIR payloads exchanged with external systems."""
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'

    class Status(models.TextChoices):
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        QUEUED = 'queued', 'Queued'
        FAILED = 'failed', 'Failed'

    source_system = models.CharField(max_length=120, blank=True)
    destination_system = models.CharField(max_length=120, blank=True)
    direction = models.CharField(max_length=20, choices=Direction.choices, default=Direction.INBOUND)
    message_type = models.CharField(max_length=50, default='unknown')
    protocol = models.CharField(max_length=20, default='fhir', choices=[('fhir', 'FHIR'), ('hl7', 'HL7')])
    resource_type = models.CharField(max_length=50, blank=True)
    correlation_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACCEPTED)
    payload = models.JSONField(default=dict, blank=True)
    raw_payload = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='integration_messages', null=True, blank=True)
    client = models.ForeignKey(IntegrationClient, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.protocol.upper()} {self.message_type} {self.status}'


class MirthChannel(BaseModel):
    """Tenant-owned connection metadata for an external Mirth Connect channel.

    Mirth performs device-specific HL7 v2 parsing and mapping. HMS stores only
    the channel contract and receives normalized FHIR/JSON messages.
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        ERROR = 'error', 'Error'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='mirth_channels')
    client = models.ForeignKey(IntegrationClient, on_delete=models.PROTECT, related_name='mirth_channels')
    name = models.CharField(max_length=120)
    source_system = models.CharField(max_length=120)
    protocol = models.CharField(max_length=20, choices=[('hl7', 'HL7 v2'), ('fhir', 'FHIR')], default='hl7')
    direction = models.CharField(max_length=20, choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')], default='inbound')
    mirth_base_url = models.URLField(blank=True)
    channel_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_health_check = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='unique_mirth_channel_per_tenant'),
        ]

    def __str__(self):
        return f'{self.name} ({self.source_system})'
