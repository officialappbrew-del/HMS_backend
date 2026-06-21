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
    """Audit log for all system activities."""
    user = models.ForeignKey('users.GlobalUser', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.action} - {self.resource_type} - {self.timestamp}"
    
    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']


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