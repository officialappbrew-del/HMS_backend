import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.utils import timezone
from django.conf import settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import base64

from core.models import BaseModel, EncryptedField


class GlobalUser(AbstractUser):
    """Global user model for system administrators."""
    class GlobalRole(models.TextChoices):
        SUPER_ADMIN = 'super_admin', _('Super Administrator')
        SYSTEM_ADMIN = 'system_admin', _('System Administrator')
        SUPPORT = 'support', _('Support Staff')
        AUDITOR = 'auditor', _('Auditor')
    
    # Override default fields
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[AbstractUser.username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    email = models.EmailField(_('email address'), unique=True)
    
    # Additional fields
    role = models.CharField(
        max_length=20,
        choices=GlobalRole.choices,
        default=GlobalRole.SYSTEM_ADMIN
    )
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    phone = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be entered in the format: '+2348012345678'. Up to 15 digits allowed."
            )
        ],
        blank=True
    )
    
    # Security fields
    rsa_public_key = models.TextField(null=True, blank=True)
    two_fa_enabled = models.BooleanField(default=True)
    two_fa_method = models.CharField(
        max_length=20,
        choices=[
            ('totp', 'TOTP (Google Authenticator)'),
            ('sms', 'SMS'),
            ('email', 'Email'),
            ('none', 'None'),
        ],
        default='totp'
    )
    two_fa_secret = EncryptedField(null=True, blank=True)
    backup_codes = EncryptedField(null=True, blank=True)  # JSON list of backup codes
    
    # Security tracking
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)
    last_security_alert = models.DateTimeField(null=True, blank=True)
    
    # Global permissions
    can_create_tenants = models.BooleanField(default=False)
    can_suspend_tenants = models.BooleanField(default=False)
    can_delete_tenants = models.BooleanField(default=False)
    can_view_all_tenants = models.BooleanField(default=False)
    
    # Metadata
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users'
    )
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    class Meta:
        verbose_name = _('Global User')
        verbose_name_plural = _('Global Users')
        ordering = ['-date_joined']
    
    def generate_rsa_keys(self):
        """Generate RSA key pair for the user."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        # Save public key
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.rsa_public_key = public_pem.decode()
        
        # Encrypt and save private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        return private_pem.decode()
    
    def is_account_locked(self):
        """Check if account is locked."""
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False
    
    def lock_account(self, duration_minutes=30):
        """Lock account for specified duration."""
        self.account_locked_until = timezone.now() + timezone.timedelta(minutes=duration_minutes)
        self.save(update_fields=['account_locked_until'])
    
    def unlock_account(self):
        """Unlock account."""
        self.account_locked_until = None
        self.login_attempts = 0
        self.save(update_fields=['account_locked_until', 'login_attempts'])
    
    def record_login_attempt(self, ip_address, successful=False):
        """Record login attempt."""
        if successful:
            self.login_attempts = 0
            self.last_login_ip = ip_address
            self.last_login = timezone.now()
        else:
            self.login_attempts += 1
            if self.login_attempts >= 5:
                self.lock_account()
        self.save()


class User2FA(BaseModel):
    """Two-factor authentication settings for users."""
    class TwoFAMethod(models.TextChoices):
        TOTP = 'totp', _('TOTP (Google Authenticator)')
        SMS = 'sms', _('SMS')
        EMAIL = 'email', _('Email')
        PUSH = 'push', _('Push Notification')
    
    user = models.OneToOneField(
        GlobalUser,
        on_delete=models.CASCADE,
        related_name='two_fa_settings'
    )
    method = models.CharField(
        max_length=20,
        choices=TwoFAMethod.choices,
        default=TwoFAMethod.TOTP
    )
    is_enabled = models.BooleanField(default=True)
    
    # TOTP settings
    totp_secret = EncryptedField(null=True, blank=True)
    totp_verified = models.BooleanField(default=False)
    
    # SMS settings
    sms_phone = models.CharField(max_length=15, blank=True)
    sms_verified = models.BooleanField(default=False)
    
    # Email settings
    backup_email = models.EmailField(blank=True)
    email_verified = models.BooleanField(default=False)
    
    # Backup codes (encrypted JSON array)
    backup_codes = EncryptedField(null=True, blank=True)
    backup_codes_generated_at = models.DateTimeField(null=True, blank=True)
    
    # Security settings
    require_2fa_for_login = models.BooleanField(default=True)
    allow_remember_device = models.BooleanField(default=True)
    trusted_devices = models.JSONField(default=list, blank=True)
    
    # Usage tracking
    last_used = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.IntegerField(default=0)
    last_failed_attempt = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"2FA Settings for {self.user.username}"
    
    def generate_backup_codes(self, count=10):
        """Generate backup codes for 2FA recovery."""
        import secrets
        codes = [secrets.token_hex(4) for _ in range(count)]
        self.backup_codes = codes
        self.backup_codes_generated_at = timezone.now()
        self.save()
        return codes
    
    def verify_backup_code(self, code):
        """Verify a backup code."""
        if not self.backup_codes:
            return False
        
        if code in self.backup_codes:
            # Remove used code
            codes = self.backup_codes
            codes.remove(code)
            self.backup_codes = codes
            self.save()
            return True
        return False
    
    def get_available_methods(self):
        """Get available 2FA methods for this user."""
        methods = []
        if self.method == self.TwoFAMethod.TOTP and self.totp_verified:
            methods.append(self.TwoFAMethod.TOTP)
        if self.method == self.TwoFAMethod.SMS and self.sms_verified:
            methods.append(self.TwoFAMethod.SMS)
        if self.method == self.TwoFAMethod.EMAIL and self.email_verified:
            methods.append(self.TwoFAMethod.EMAIL)
        return methods


class RSAKey(BaseModel):
    """RSA key management for users."""
    user = models.ForeignKey(
        GlobalUser,
        on_delete=models.CASCADE,
        related_name='rsa_keys'
    )
    key_name = models.CharField(max_length=100)
    public_key = models.TextField()
    private_key_encrypted = EncryptedField()
    key_fingerprint = models.CharField(max_length=128, unique=True)
    key_size = models.IntegerField(default=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    
    # Key metadata
    algorithm = models.CharField(max_length=20, default='RSA')
    key_usage = models.JSONField(default=list)  # ['sign', 'encrypt', 'verify']
    is_primary = models.BooleanField(default=False)
    
    def __str__(self):
        return f"RSA Key {self.key_name} for {self.user.username}"
    
    class Meta:
        verbose_name = _('RSA Key')
        verbose_name_plural = _('RSA Keys')
        ordering = ['-is_primary', '-created_at']
    
    def save(self, *args, **kwargs):
        # Generate fingerprint if not set
        if not self.key_fingerprint:
            import hashlib
            fingerprint = hashlib.sha256(self.public_key.encode()).hexdigest()
            self.key_fingerprint = fingerprint
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if key is expired."""
        return timezone.now() > self.expires_at
    
    def rotate_key(self):
        """Generate new key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        # Update keys
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        self.public_key = public_pem.decode()
        self.private_key_encrypted = private_pem.decode()
        self.expires_at = timezone.now() + timezone.timedelta(days=365)  # 1 year
        self.save()


class UserSession(BaseModel):
    """Track user sessions for security."""
    user = models.ForeignKey(
        GlobalUser,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    session_key = models.CharField(max_length=128, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_info = models.JSONField(default=dict, blank=True)
    location_info = models.JSONField(default=dict, blank=True)
    
    # Session state
    is_active = models.BooleanField(default=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    
    # Security flags
    requires_reauth = models.BooleanField(default=False)
    is_trusted_device = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Session {self.session_key[:10]}... for {self.user.username}"
    
    class Meta:
        verbose_name = _('User Session')
        verbose_name_plural = _('User Sessions')
        ordering = ['-last_activity']
    
    def is_expired(self):
        """Check if session is expired."""
        return timezone.now() > self.expires_at
    
    def terminate(self):
        """Terminate session."""
        self.is_active = False
        self.save()


class SecurityEvent(BaseModel):
    """Log security events for monitoring."""
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = 'login_success', _('Successful Login')
        LOGIN_FAILED = 'login_failed', _('Failed Login')
        LOGOUT = 'logout', _('Logout')
        PASSWORD_CHANGE = 'password_change', _('Password Changed')
        PASSWORD_RESET = 'password_reset', _('Password Reset')
        TWO_FA_ENABLED = '2fa_enabled', _('2FA Enabled')
        TWO_FA_DISABLED = '2fa_disabled', _('2FA Disabled')
        ACCOUNT_LOCKED = 'account_locked', _('Account Locked')
        ACCOUNT_UNLOCKED = 'account_unlocked', _('Account Unlocked')
        RSA_KEY_GENERATED = 'rsa_key_generated', _('RSA Key Generated')
        RSA_KEY_REVOKED = 'rsa_key_revoked', _('RSA Key Revoked')
        SUSPICIOUS_ACTIVITY = 'suspicious_activity', _('Suspicious Activity')
    
    class Severity(models.TextChoices):
        INFO = 'info', _('Information')
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        CRITICAL = 'critical', _('Critical')
    
    user = models.ForeignKey(
        GlobalUser,
        on_delete=models.CASCADE,
        related_name='security_events',
        null=True,
        blank=True
    )
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    description = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        GlobalUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_events'
    )
    resolution_notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.get_event_type_display()} - {self.user.username if self.user else 'System'}"
    
    class Meta:
        verbose_name = _('Security Event')
        verbose_name_plural = _('Security Events')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['severity', 'resolved']),
        ]


class UserNotification(BaseModel):
    """User notifications system."""
    class NotificationType(models.TextChoices):
        SECURITY = 'security', _('Security Alert')
        SYSTEM = 'system', _('System Notification')
        ACCOUNT = 'account', _('Account Notification')
        CLINICAL = 'clinical', _('Clinical Alert')
        BILLING = 'billing', _('Billing Notification')
        GENERAL = 'general', _('General Notification')
    
    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        URGENT = 'urgent', _('Urgent')
    
    user = models.ForeignKey(
        GlobalUser,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    
    # Delivery status
    sent_via_email = models.BooleanField(default=False)
    sent_via_sms = models.BooleanField(default=False)
    sent_via_push = models.BooleanField(default=False)
    sent_via_system = models.BooleanField(default=True)
    
    # Read status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Action tracking
    action_taken = models.BooleanField(default=False)
    action_taken_at = models.DateTimeField(null=True, blank=True)
    action_notes = models.TextField(blank=True)
    
    # Expiry
    expires_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"
    
    class Meta:
        verbose_name = _('User Notification')
        verbose_name_plural = _('User Notifications')
        ordering = ['-created_at', 'priority']
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
    
    def is_expired(self):
        """Check if notification is expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False