import uuid
from datetime import date, datetime
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.conf import settings
from django_tenants.models import TenantMixin, DomainMixin

from core.models import BaseModel, Country, State, LGA, FacilityType


class Tenant(BaseModel):
    """Healthcare facility/tenant model."""
    class SubscriptionStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        TRIAL = 'trial', _('Trial')
        SUSPENDED = 'suspended', _('Suspended')
        CANCELLED = 'cancelled', _('Cancelled')
        EXPIRED = 'expired', _('Expired')
    
    class NHISAccreditation(models.TextChoices):
        NOT_APPLIED = 'not_applied', _('Not Applied')
        PENDING = 'pending', _('Pending')
        ACCREDITED = 'accredited', _('Accredited')
        REJECTED = 'rejected', _('Rejected')
        SUSPENDED = 'suspended', _('Suspended')
    
    # Basic Information
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=50, unique=True)
    domain = models.CharField(max_length=200, unique=True)
    schema_name = models.CharField(max_length=100, unique=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    is_active = models.BooleanField(default=True)
    
    # Contact Information
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    phone2 = models.CharField(max_length=20, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    # state = models.ForeignKey(State, on_delete=models.PROTECT)
    state = models.ForeignKey('core.State', on_delete=models.PROTECT, null=True, blank=True)  # Make nullable
    lga = models.ForeignKey(LGA, on_delete=models.PROTECT, null=True, blank=True)
    country = models.ForeignKey('core.Country', on_delete=models.PROTECT, default=1, related_name='tenants') 
    
    # Facility Details
    facility_type = models.ForeignKey(FacilityType, on_delete=models.PROTECT)
    registration_number = models.CharField(max_length=100, unique=True)
    tax_id = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    
    # Subscription & Billing
    subscription_plan = models.ForeignKey('SubscriptionPlan', on_delete=models.PROTECT)
    subscription_status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL
    )
    subscription_start_date = models.DateField(default=date.today)
    subscription_end_date = models.DateField(null=True, blank=True)
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=50, blank=True)
    billing_email = models.EmailField(blank=True)
    
    # NHIS Integration
    nhis_accreditation = models.CharField(
        max_length=20,
        choices=NHISAccreditation.choices,
        default=NHISAccreditation.NOT_APPLIED
    )
    nhis_provider_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    nhis_accreditation_date = models.DateField(null=True, blank=True)
    nhis_expiry_date = models.DateField(null=True, blank=True)
    
    # Operational Details
    bed_capacity = models.IntegerField(default=0)
    established_date = models.DateField(null=True, blank=True)
    operating_hours = models.JSONField(default=dict, blank=True)
    emergency_services = models.BooleanField(default=False)
    
    # Settings & Configuration
    config = models.JSONField(default=dict, blank=True)
    features = models.JSONField(default=dict, blank=True)

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tenants',
        db_index=True,
    )


    notes = models.TextField(blank=True)
    logo = models.ImageField(upload_to='tenant_logos/', null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')
        ordering = ['name']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['schema_name']),
            models.Index(fields=['subscription_status']),
            models.Index(fields=['nhis_accreditation']),
        ]
    
    def save(self, *args, **kwargs):
        # Normalize empty values so they do not violate unique constraints
        if self.nhis_provider_id == '':
            self.nhis_provider_id = None

        # Normalize date fields so datetime values do not break serializer output
        for field_name in (
            'subscription_start_date',
            'subscription_end_date',
            'nhis_accreditation_date',
            'nhis_expiry_date',
            'established_date'
        ):
            value = getattr(self, field_name, None)
            if isinstance(value, datetime):
                setattr(self, field_name, value.date())

        # Generate code if not provided
        if not self.code:
            self.code = self.generate_tenant_code()
        
        # Generate schema name if not provided
        if not self.schema_name:
            self.schema_name = self.generate_schema_name()
        
        super().save(*args, **kwargs)
    
    def generate_tenant_code(self):
        """Generate unique tenant code."""
        import random
        import string
        
        # Use first 3 letters of name + random numbers
        name_part = self.name[:3].upper()
        random_part = ''.join(random.choices(string.digits, k=4))
        return f"{name_part}{random_part}"
    
    def generate_schema_name(self):
        """Generate schema name from tenant code."""
        return f"tenant_{self.code.lower()}"
    
    def is_subscription_active(self):
        """Check if tenant is active by subscription and status."""
        return (
            self.subscription_status == self.SubscriptionStatus.ACTIVE and
            self.is_active
        )
    
    def is_trial(self):
        """Check if tenant is in trial period."""
        return self.subscription_status == self.SubscriptionStatus.TRIAL
    
    def days_remaining_in_trial(self):
        """Calculate days remaining in trial period."""
        if not self.is_trial():
            return 0
        
        if not self.subscription_end_date:
            return 30  # Default trial period
        
        remaining = (self.subscription_end_date - timezone.now().date()).days
        return max(0, remaining)

    @property
    def days_remaining(self):
        """Calculate days remaining in current subscription period."""
        if not self.subscription_end_date:
            return None
        remaining = (self.subscription_end_date - timezone.now().date()).days
        return max(0, remaining)

    @property
    def is_subscription_expiring_soon(self):
        """Check if subscription is expiring within 30 days."""
        days = self.days_remaining
        return days is not None and 0 <= days <= 30
    
    def create_schema(self):
        """Provision this tenant's PostgreSQL schema.

        Creates the schema and runs the tenant-app migrations into it. This is
        best-effort: the ``CREATE SCHEMA`` is always performed (idempotent), and
        the migration run is attempted with the django-tenants ``schema_context``
        helper so shared tables stay in ``public``. Any migration failure is
        logged and swallowed so callers (e.g. self-service signup) are not
        broken by a provisioning hiccup; a background ``migrate_schemas`` run
        will reconcile any missing tables.
        """
        import logging
        from django.db import connection
        from django.core.management import call_command
        logger = logging.getLogger(__name__)

        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS %s' % connection.ops.quote_name(self.schema_name))

        try:
            from django_tenants.utils import schema_context
            with schema_context(self.schema_name):
                call_command('migrate_schemas', schema_name=self.schema_name,
                             interactive=False, verbosity=0)
        except Exception as exc:
            logger.warning('migrate_schemas skipped for schema %s: %s', self.schema_name, exc)

        try:
            connection.set_schema_to_public()
        except Exception:
            pass
        return True

    def delete_schema(self):
        """Drop this tenant's PostgreSQL schema (and its objects)."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('DROP SCHEMA IF EXISTS %s CASCADE' % connection.ops.quote_name(self.schema_name))
        try:
            connection.set_schema_to_public()
        except Exception:
            pass
        return True


class SubscriptionPayment(BaseModel):
    """Platform subscription payment tracked in the public schema."""
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SUCCESS = 'success', _('Success')
        FAILED = 'failed', _('Failed')

    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, null=True, blank=True,
        related_name='subscription_payments'
    )
    plan = models.ForeignKey('SubscriptionPlan', on_delete=models.PROTECT, related_name='subscription_payments')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    billing_period = models.CharField(max_length=20, default='monthly')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    gateway = models.CharField(max_length=30, default='paystack')
    gateway_response = models.JSONField(default=dict, blank=True)
    signup_data = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]


class SubscriptionExpiryNotification(BaseModel):
    """Track subscription expiry notifications sent to tenants."""
    class NotificationType(models.TextChoices):
        ONE_MONTH = '1_month', _('1 Month Before Expiry')
        TWO_WEEKS = '2_weeks', _('2 Weeks Before Expiry')
        THREE_DAYS = '3_days', _('3 Days Before Expiry')
        DEADLINE = 'deadline', _('On Expiry Date')

    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='expiry_notifications')
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    sent_at = models.DateTimeField(auto_now_add=True)
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_sent = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('Subscription Expiry Notification')
        verbose_name_plural = _('Subscription Expiry Notifications')
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['tenant', 'notification_type', '-sent_at']),
            models.Index(fields=['tenant', '-sent_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'notification_type'],
                condition=models.Q(is_sent=True),
                name='unique_sent_notification_per_tenant_per_type'
            )
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.get_notification_type_display()}"


class TenantDomain(DomainMixin):
    pass

class SubscriptionPlan(BaseModel):
    """Subscription plans for tenants."""
    class BillingPeriod(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        QUARTERLY = 'quarterly', _('Quarterly')
        YEARLY = 'yearly', _('Yearly')
    
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    # Pricing
    price_monthly = models.DecimalField(max_digits=12, decimal_places=2)
    price_quarterly = models.DecimalField(max_digits=12, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    
    # Service costs (third-party platforms)
    email_service_cost_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='Cost of email service provider per month')
    sms_service_cost_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='Cost of SMS service provider per month')
    service_providers = models.JSONField(default=dict, blank=True, help_text='Configured service providers, e.g. {"email": "sendgrid", "sms": "twilio"}')
    
    # Limits
    max_users = models.IntegerField(default=5)
    max_patients = models.IntegerField(default=1000)
    max_storage_gb = models.IntegerField(default=10)
    max_api_calls_per_day = models.IntegerField(default=10000)
    email_limit_monthly = models.IntegerField(default=1000, help_text='Max emails per month')
    sms_limit_monthly = models.IntegerField(default=500, help_text='Max SMS per month')
    
    # Features
    features = models.JSONField(default=dict, blank=True)
    modules = models.JSONField(default=list, blank=True)
    
    # Trial
    trial_period_days = models.IntegerField(default=30)
    is_trial_available = models.BooleanField(default=True)
    
    # Metadata
    is_default = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - ₦{self.price_monthly}/month"
    
    class Meta:
        verbose_name = _('Subscription Plan')
        verbose_name_plural = _('Subscription Plans')
        ordering = ['display_order', 'price_monthly']


class TenantUser(BaseModel):
    """Tenant-scoped user model."""
    class UserRole(models.TextChoices):
        ADMIN = 'admin', _('Administrator')
        DOCTOR = 'doctor', _('Doctor')
        NURSE = 'nurse', _('Nurse')
        PHARMACIST = 'pharmacist', _('Pharmacist')
        LAB_TECH = 'lab_tech', _('Lab Technician')
        LAB_MANAGER = 'lab_manager', _('Lab Manager')
        RECEPTIONIST = 'receptionist', _('Receptionist')
        ACCOUNTANT = 'accountant', _('Accountant')
        HR_MANAGER = 'hr_manager', _('HR Manager')
        INVENTORY_MANAGER = 'inventory_manager', _('Inventory Manager')
        PATIENT = 'patient', _('Patient')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users')
    
    # Authentication
    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # Contact Information
    phone = models.CharField(max_length=20)
    phone2 = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Employment Details
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    role = models.CharField(max_length=50, choices=UserRole.choices)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    designation = models.CharField(max_length=100, blank=True)
    employment_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
        ('retired', 'Retired')
    ], default='active', db_index=True)
    
    # Professional Details (for medical staff)
    qualification = models.TextField(blank=True)
    specialization = models.ForeignKey('core.Specialization', on_delete=models.SET_NULL, null=True, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    license_expiry = models.DateField(null=True, blank=True)
    mdcn_number = models.CharField(max_length=50, blank=True)  # For doctors in Nigeria
    
    # Security
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_root_admin = models.BooleanField(default=False, db_index=True)
    created_by_invitation = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    # Token invalidation version. Incremented on password change/reset so that
    # previously issued JWTs become invalid immediately.
    token_version = models.IntegerField(default=1)
    
    # Settings
    preferences = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='Africa/Lagos')
    
    # Global Access (if this user also has global access)
    global_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tenant_user'
    )
    is_global_admin = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.username or self.employee_id} ({self.tenant.code})"
    
    class Meta:
        verbose_name = _('Tenant User')
        verbose_name_plural = _('Tenant Users')
        unique_together = [['tenant', 'username'], ['tenant', 'email']]
        ordering = ['tenant', 'username', 'email']
        indexes = [
            models.Index(fields=['tenant', 'username']),
            models.Index(fields=['tenant', 'email']),
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['tenant', 'employee_id']),
            models.Index(fields=['tenant', 'is_root_admin']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant'],
                condition=Q(is_root_admin=True),
                name='unique_root_admin_per_tenant'
            )
        ]
    
    def save(self, *args, **kwargs):
        # Auto-generate a login-friendly identifier if missing.
        if not self.employee_id:
            import uuid
            role_part = (self.role or 'staff')[:3].upper()
            tenant_part = (self.tenant.code if self.tenant_id else 'TN')[:3].upper()
            self.employee_id = f"{tenant_part}-{role_part}-{uuid.uuid4().hex[:6].upper()}"

        if not self.username:
            self.username = self.employee_id

        super().save(*args, **kwargs)

    def get_full_name(self):
        """Return the full name of the user."""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def set_password(self, raw_password):
        """Set password for the user."""
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)
        self.password_changed_at = timezone.now()
    
    def check_password(self, raw_password):
        """Check if the given password is correct."""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)
    
    def is_account_locked(self):
        """Check if account is locked."""
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False
    
    def lock_account(self, duration_minutes=30):
        """Lock account for specified duration."""
        self.account_locked_until = timezone.now() + timezone.timedelta(minutes=duration_minutes)
        self.save()
    
    def unlock_account(self):
        """Unlock account."""
        self.account_locked_until = None
        self.failed_login_attempts = 0
        self.save()


class Department(BaseModel):
    """Departments within a tenant."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    
    # Department Head
    head = models.ForeignKey(
        TenantUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments'
    )
    
    # Contact Information
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    # Settings
    color = models.CharField(max_length=7, default='#007bff')  # Hex color
    is_clinical = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.name} ({self.tenant.code})"
    
    class Meta:
        verbose_name = _('Department')
        verbose_name_plural = _('Departments')
        unique_together = [['tenant', 'code']]
        ordering = ['name']


class TenantSetting(BaseModel):
    """Tenant-specific settings."""
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='settings_config')
    
    # General Settings
    system_name = models.CharField(max_length=100, default='SmartCare HMS')
    system_logo = models.ImageField(upload_to='tenant_system_logos/', null=True, blank=True)
    favicon = models.ImageField(upload_to='tenant_favicons/', null=True, blank=True)
    theme_color = models.CharField(max_length=7, default='#007bff')
    
    # Clinical Settings
    default_clinic = models.CharField(max_length=100, blank=True, default='Main Clinic')
    default_ward = models.CharField(max_length=100, blank=True, default='General Ward')

    vitals_units = models.JSONField(default=dict, blank=True)  # e.g., {"temperature": "celsius", "weight": "kg"}
    
    # Billing Settings
    currency = models.CharField(max_length=3, default='NGN')
    currency_symbol = models.CharField(max_length=5, default='₦')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=7.5)  # VAT in Nigeria
    billing_cycle = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly')
    ], default='monthly')
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    
    # Security Settings
    password_policy = models.JSONField(default=dict, blank=True)
    session_timeout = models.IntegerField(default=30)  # minutes
    max_login_attempts = models.IntegerField(default=5)
    require_2fa = models.BooleanField(default=False)
    
    # NHIS Settings
    nhis_enabled = models.BooleanField(default=False)
    nhis_default_tariff = models.CharField(max_length=50, blank=True)
    nhis_claim_submission_days = models.IntegerField(default=7)
    
    # Backup Settings
    auto_backup = models.BooleanField(default=True)
    backup_frequency = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ], default='daily')
    backup_retention_days = models.IntegerField(default=30)
    
    # Custom Fields
    custom_settings = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"Settings for {self.tenant.name}"
    
    class Meta:
        verbose_name = _('Tenant Setting')
        verbose_name_plural = _('Tenant Settings')


class TenantModule(BaseModel):
    """Modules enabled for a tenant."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='modules')
    module_name = models.CharField(max_length=100)
    module_code = models.CharField(max_length=50)
    is_enabled = models.BooleanField(default=True)
    enabled_date = models.DateTimeField(null=True, blank=True)
    disabled_date = models.DateTimeField(null=True, blank=True)
    
    # Configuration
    config = models.JSONField(default=dict, blank=True)
    
    # Limits
    user_limit = models.IntegerField(null=True, blank=True)
    storage_limit_mb = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.module_name} - {self.tenant.name}"
    
    class Meta:
        verbose_name = _('Tenant Module')
        verbose_name_plural = _('Tenant Modules')
        unique_together = [['tenant', 'module_code']]


class TenantInvitation(BaseModel):
    """Invitations for users to join a tenant."""
    class InvitationStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        EXPIRED = 'expired', _('Expired')
        REVOKED = 'revoked', _('Revoked')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=50, choices=TenantUser.UserRole.choices)
    token = models.CharField(max_length=100, unique=True)
    invited_by = models.ForeignKey(
        TenantUser,
        on_delete=models.CASCADE,
        related_name='sent_invitations'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING
    )
    archived = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    
    # Metadata
    message = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"Invitation for {self.email} to {self.tenant.name}"
    
    class Meta:
        verbose_name = _('Tenant Invitation')
        verbose_name_plural = _('Tenant Invitations')
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        # Generate token if not provided
        if not self.token:
            import secrets
            self.token = secrets.token_urlsafe(32)
        
        # Set expiry (default 7 days)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if invitation is expired."""
        return timezone.now() > self.expires_at
    
    def accept(self, user_data):
        """Accept the invitation and create user."""
        if self.status != self.InvitationStatus.PENDING:
            raise ValueError("Invitation is not pending")
        
        if self.is_expired():
            self.status = self.InvitationStatus.EXPIRED
            self.save()
            raise ValueError("Invitation has expired")
        
        # Create user as pending approval so admins must activate it before login.
        user = TenantUser.objects.create(
            tenant=self.tenant,
            email=user_data.get('email', self.email),
            username=user_data.get('username', self.email.split('@')[0]),
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            role=user_data.get('role', self.role),
            department=self.department,
            is_active=False,
            created_by_invitation=True,
            phone=user_data.get('phone', '')
        )
        
        # Set password if provided
        password = user_data.get('password')
        if password:
            user.set_password(password)
            user.save()
        
        # Update invitation status
        self.status = self.InvitationStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save()
        
        return user


class TenantActivityLog(BaseModel):
    """Activity logs for tenant operations."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='activity_logs')
    user = models.ForeignKey(TenantUser, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Activity Details
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50)
    
    # Data Changes
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    
    # Technical Details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_info = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.action} - {self.resource_type} - {self.created_at}"
    
    class Meta:
        verbose_name = _('Tenant Activity Log')
        verbose_name_plural = _('Tenant Activity Logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'user', 'created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]


class BulkTenantUserUpload(BaseModel):
    """Track bulk tenant user (staff) uploads processed in background."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='bulk_user_uploads')
    uploaded_by = models.ForeignKey('tenants.TenantUser', on_delete=models.SET_NULL, null=True, related_name='bulk_user_uploads')
    file = models.FileField(upload_to='bulk_uploads/')
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    total_records = models.IntegerField(default=0)
    processed_records = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    errors = models.JSONField(blank=True, null=True, help_text='List of row-level errors')
    result_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Bulk Tenant User Upload')
        verbose_name_plural = _('Bulk Tenant User Uploads')
        ordering = ['-created_at']

    def __str__(self):
        return f"Bulk user upload {self.id} - {self.original_filename}"


class TenantBackup(BaseModel):
    """Backup records for tenant data."""
    class BackupType(models.TextChoices):
        FULL = 'full', _('Full Backup')
        INCREMENTAL = 'incremental', _('Incremental Backup')
        DATABASE_ONLY = 'database_only', _('Database Only')
        FILES_ONLY = 'files_only', _('Files Only')
    
    class BackupStatus(models.TextChoices):
        STARTED = 'started', _('Started')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')
        PARTIAL = 'partial', _('Partial')
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='backups')
    
    # Backup Details
    backup_type = models.CharField(max_length=20, choices=BackupType.choices)
    status = models.CharField(max_length=20, choices=BackupStatus.choices)
    
    # Storage
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)  # in bytes
    storage_location = models.CharField(max_length=200, blank=True)
    
    # Timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    
    # Metadata
    checksum = models.CharField(max_length=128, blank=True)  # SHA-512
    compression_type = models.CharField(max_length=50, default='gzip')
    encryption_key_id = models.CharField(max_length=100, blank=True)
    
    # Error Handling
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.backup_type} backup for {self.tenant.name} - {self.status}"
    
    class Meta:
        verbose_name = _('Tenant Backup')
        verbose_name_plural = _('Tenant Backups')
        ordering = ['-start_time']
    
    def save(self, *args, **kwargs):
        # Calculate duration if both start and end times are set
        if self.start_time and self.end_time:
            self.duration = self.end_time - self.start_time
        super().save(*args, **kwargs)


class CommunicationProfile(BaseModel):
    """Per-tenant communication identity for email and SMS."""
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='communication_profile')
    is_active = models.BooleanField(default=True)
    
    # Email identity
    email_from = models.EmailField(blank=True, help_text='Verified sender email address, e.g. no-reply@hospital.org')
    from_name = models.CharField(max_length=200, blank=True, help_text="Display name for the sender, e.g. St. Mary's Hospital")
    reply_to = models.EmailField(blank=True, help_text='Where replies should be delivered')
    verified_domain = models.CharField(max_length=200, blank=True, help_text='Verified sending domain or subdomain')
    email_provider = models.CharField(max_length=50, blank=True, help_text='sendgrid|ses|smtp|default')
    email_username = models.CharField(max_length=200, blank=True)
    email_password = models.CharField(max_length=200, blank=True, help_text='Encrypted at rest')
    email_host = models.CharField(max_length=200, blank=True)
    email_port = models.IntegerField(null=True, blank=True)
    email_use_tls = models.BooleanField(default=True)
    
    # SMS identity
    sms_provider = models.CharField(max_length=50, blank=True, help_text='twilio|messagebird|vonage|default')
    sms_sender_id = models.CharField(max_length=20, blank=True, help_text='Alphanumeric sender ID or phone number')
    sms_phone_number = models.CharField(max_length=20, blank=True)
    sms_api_key = models.CharField(max_length=200, blank=True, help_text='Encrypted at rest')
    sms_country_code = models.CharField(max_length=10, blank=True, default='NG')
    
    # Compliance & templates
    consent_tracking_enabled = models.BooleanField(default=True)
    opt_out_message = models.CharField(max_length=200, blank=True, default='Reply STOP to unsubscribe')
    dnd_enabled = models.BooleanField(default=False)
    message_templates = models.JSONField(default=dict, blank=True, help_text='Pre-approved message templates per channel/type')
    
    # Channel toggles & limits
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)
    daily_email_limit = models.IntegerField(default=1000)
    daily_sms_limit = models.IntegerField(default=500)
    
    def save(self, *args, **kwargs):
        """Encrypt email password and SMS API key at rest (idempotent)."""
        from .security import encrypt_value, is_encrypted
        if self.email_password and not is_encrypted(self.email_password):
            self.email_password = encrypt_value(self.email_password)
        if self.sms_api_key and not is_encrypted(self.sms_api_key):
            self.sms_api_key = encrypt_value(self.sms_api_key)
        super().save(*args, **kwargs)

    def get_decrypted_email_password(self):
        """Return the decrypted email password (never stored in plaintext)."""
        from .security import decrypt_value
        return decrypt_value(self.email_password)

    def get_decrypted_sms_api_key(self):
        """Return the decrypted SMS API key (never stored in plaintext)."""
        from .security import decrypt_value
        return decrypt_value(self.sms_api_key)

    def __str__(self):
        return f"Communication profile for {self.tenant.name}"
    
    class Meta:
        verbose_name = _('Communication Profile')
        verbose_name_plural = _('Communication Profiles')


class ExternalServiceProfile(BaseModel):
    """Tenant-scoped endpoints and encrypted credentials for connected systems."""
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='external_service_profile')
    mirth_endpoint = models.URLField(blank=True)
    mirth_channel_id = models.CharField(max_length=120, blank=True)
    mirth_api_key = models.CharField(max_length=255, blank=True)
    lis_endpoint = models.URLField(blank=True)
    lis_api_key = models.CharField(max_length=255, blank=True)
    pacs_endpoint = models.URLField(blank=True)
    pacs_api_key = models.CharField(max_length=255, blank=True)
    fhir_endpoint = models.URLField(blank=True)
    fhir_api_key = models.CharField(max_length=255, blank=True)

    SECRET_FIELDS = ('mirth_api_key', 'lis_api_key', 'pacs_api_key', 'fhir_api_key')

    def save(self, *args, **kwargs):
        from .security import encrypt_value, is_encrypted
        for field_name in self.SECRET_FIELDS:
            value = getattr(self, field_name)
            if value and not is_encrypted(value):
                setattr(self, field_name, encrypt_value(value))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('External Service Profile')
        verbose_name_plural = _('External Service Profiles')


class SupportTicket(BaseModel):
    """Support ticket for tenant technical issues."""
    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        CRITICAL = 'critical', _('Critical')
    
    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        IN_PROGRESS = 'in_progress', _('In Progress')
        RESOLVED = 'resolved', _('Resolved')
        CLOSED = 'closed', _('Closed')
    
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_by_name = models.CharField(max_length=100, help_text="Name of person who created the ticket")
    created_by_email = models.EmailField(help_text="Email of person who created the ticket")
    created_by_role = models.CharField(max_length=50, help_text="Role of creator (e.g. admin, receptionist)")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_tickets'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = _('Support Ticket')
        verbose_name_plural = _('Support Tickets')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status', '-created_at']),
            models.Index(fields=['priority', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} - {self.tenant.name}"