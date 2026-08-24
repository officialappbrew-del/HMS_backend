from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from cryptography.fernet import Fernet
import base64
from decouple import config

class BaseModel(models.Model):
    """Base model with common fields."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        abstract = True


class EncryptedField(models.TextField):
    """Custom field for encrypted data storage."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fernet = self.get_fernet()
    
    def get_fernet(self):
        encryption_key = config('ENCRYPTION_KEY', default='default-encryption-key-32-chars-long-here')
        if len(encryption_key) != 32:
            # Pad or truncate to 32 characters
            if len(encryption_key) < 32:
                encryption_key = encryption_key.ljust(32, '0')
            else:
                encryption_key = encryption_key[:32]
        
        key = base64.urlsafe_b64encode(encryption_key.encode())
        return Fernet(key)
    
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except:
            # If decryption fails, return the raw value
            # (for cases where data might not be encrypted yet)
            return value
    
    def get_prep_value(self, value):
        if value is None:
            return value
        
        encrypted_value = self.fernet.encrypt(value.encode())
        return encrypted_value.decode()


class Country(models.Model):
    """Country model for internationalization."""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2, unique=True)
    phone_code = models.CharField(max_length=10)
    currency = models.CharField(max_length=3)
    timezone = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = _('Country')
        verbose_name_plural = _('Countries')
        ordering = ['name']


class State(models.Model):
    """State model for Nigeria."""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        verbose_name = _('State')
        verbose_name_plural = _('States')
        ordering = ['name']


class LGA(models.Model):
    """Local Government Area model."""
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='lgas')
    
    def __str__(self):
        return f"{self.name}, {self.state.name}"
    
    class Meta:
        verbose_name = _('Local Government Area')
        verbose_name_plural = _('Local Government Areas')
        ordering = ['name']


class FacilityType(models.Model):
    """Type of healthcare facility."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=20, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = _('Facility Type')
        verbose_name_plural = _('Facility Types')
        ordering = ['name']


class Specialization(models.Model):
    """Medical specializations."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=20, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = _('Specialization')
        verbose_name_plural = _('Specializations')
        ordering = ['name']


class Language(models.Model):
    """Supported languages."""
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = _('Language')
        verbose_name_plural = _('Languages')
        ordering = ['name']


class NotificationTemplate(models.Model):
    """Templates for system notifications."""
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name='notification_templates')
    notification_type = models.CharField(max_length=50, choices=[
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('system', 'System Notification'),
    ])
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = _('Notification Template')
        verbose_name_plural = _('Notification Templates')
        ordering = ['name']


class SystemSetting(models.Model):
    """System-wide settings."""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    secret_value = EncryptedField(blank=True, default='')
    is_secret = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, default='general')
    data_type = models.CharField(max_length=20, choices=[
        ('string', 'String'),
        ('integer', 'Integer'),
        ('boolean', 'Boolean'),
        ('json', 'JSON'),
        ('float', 'Float'),
    ])
    
    def __str__(self):
        return self.key
    
    class Meta:
        verbose_name = _('System Setting')
        verbose_name_plural = _('System Settings')
        ordering = ['key']


class AuditLog(models.Model):
    """Audit trail for all system activities and events.

    Every field the activity UI surfaces is stored here: the raw
    ``action`` / ``resource_type`` / ``resource_id``, the ``actor`` who
    performed it, the ``severity`` and human ``title``, the source
    ``ip_address``, and whether the entry is ``is_verified`` (written by
    the server rather than client-supplied). New fields are nullable or
    defaulted so the many existing ``AuditLog.objects.create(...)`` calls
    across the codebase keep working unchanged.
    """

    class Severity(models.TextChoices):
        INFO = 'info', _('Info')
        WARNING = 'warning', _('Warning')
        URGENT = 'urgent', _('Urgent')

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True,
    )
    user = models.ForeignKey(
        'users.GlobalUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    action = models.CharField(max_length=50, db_index=True)
    resource_type = models.CharField(max_length=50, db_index=True)
    resource_id = models.CharField(max_length=50, db_index=True)
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.INFO,
        db_index=True,
    )
    title = models.CharField(max_length=255, blank=True)
    actor = models.CharField(max_length=255, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)
    is_verified = models.BooleanField(default=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.action} - {self.resource_type} - {self.timestamp}"

    def _humanize_action(self):
        """Return a (title, severity) pair derived from the raw action."""
        action = (self.action or '').lower()
        title = action.replace('_', ' ').title()
        severity = self.Severity.INFO

        if action.startswith(('delete', 'remove', 'deactivate', 'suspend', 'terminate')):
            severity = self.Severity.URGENT
        elif action.startswith(('warn', 'fail', 'error', 'expire', 'override', 'breach')):
            severity = self.Severity.WARNING

        return title, severity

    def save(self, *args, **kwargs):
        # Auto-populate derived fields unless explicitly provided, so both the
        # new patient-audit writer and the legacy .create() calls stay valid.
        if not self.title or not self.severity:
            title, severity = self._humanize_action()
            if not self.title:
                self.title = title
            if not self.severity:
                self.severity = severity

        if not self.actor:
            self.actor = self.user.username if self.user else ''

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'action']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['severity', 'timestamp']),
        ]


class BackupLog(models.Model):
    """Log for system backups."""
    backup_type = models.CharField(max_length=20, choices=[
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
        ('differential', 'Differential Backup'),
    ])
    status = models.CharField(max_length=20, choices=[
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ])
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.backup_type} - {self.status} - {self.start_time}"
    
    class Meta:
        verbose_name = _('Backup Log')
        verbose_name_plural = _('Backup Logs')
        ordering = ['-start_time']