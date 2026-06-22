from datetime import datetime
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
from django.utils import timezone
from django.conf import settings
import re
import jwt



from .models import (
    Tenant, SubscriptionPlan, TenantUser, Department,
    TenantSetting, TenantModule, TenantInvitation,
    TenantActivityLog, TenantBackup
)
from core.models import State, LGA, FacilityType
from core.serializers import StateSerializer, LGASerializer, FacilityTypeSerializer


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans."""
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for tenants."""
    tenant_id = serializers.UUIDField(source='public_id', read_only=True)
    state_details = StateSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    facility_type_details = FacilityTypeSerializer(source='facility_type', read_only=True)
    subscription_plan_details = SubscriptionPlanSerializer(source='subscription_plan', read_only=True)
    subscription_start_date = serializers.SerializerMethodField()
    subscription_end_date = serializers.SerializerMethodField()
    nhis_accreditation_date = serializers.SerializerMethodField()
    nhis_expiry_date = serializers.SerializerMethodField()
    established_date = serializers.SerializerMethodField()
    
    # Computed fields
    is_active_status = serializers.BooleanField(source='is_active', read_only=True)
    days_remaining_in_trial = serializers.IntegerField(read_only=True)

    def _normalize_date(self, value):
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    def get_subscription_start_date(self, obj):
        return self._normalize_date(obj.subscription_start_date)

    def get_subscription_end_date(self, obj):
        return self._normalize_date(obj.subscription_end_date)

    def get_nhis_accreditation_date(self, obj):
        return self._normalize_date(obj.nhis_accreditation_date)

    def get_nhis_expiry_date(self, obj):
        return self._normalize_date(obj.nhis_expiry_date)

    def get_established_date(self, obj):
        return self._normalize_date(obj.established_date)
    
    class Meta:
        model = Tenant
        fields = '__all__'
        read_only_fields = [
            'created_at', 'updated_at', 'code', 'schema_name', 'public_id',
            'subscription_status', 'created_by'
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('id', None)
        return data
    
    def validate_domain(self, value):
        """Validate domain format."""
        # Simple domain validation
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
        if not re.match(domain_pattern, value):
            raise serializers.ValidationError("Invalid domain format")
        return value.lower()
    
    def validate_registration_number(self, value):
        """Validate registration number format."""
        # Add specific validation for Nigerian registration numbers if needed
        return value.upper()

    def validate_nhis_provider_id(self, value):
        """Prevent empty strings from being treated as valid unique values."""
        if value == '':
            return None
        return value
    
    def create(self, validated_data):
        # Set created_by from request user
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        
        # Create tenant
        tenant = Tenant.objects.create(**validated_data)
        
        # Create default settings
        TenantSetting.objects.create(tenant=tenant)
        
        # Create default departments
        self.create_default_departments(tenant)
        
        return tenant
    
    def create_default_departments(self, tenant):
        """Create default departments for a new tenant."""
        default_departments = [
            {'name': 'Administration', 'code': 'ADMIN', 'is_clinical': False},
            {'name': 'Outpatient Department', 'code': 'OPD', 'is_clinical': True},
            {'name': 'Inpatient Department', 'code': 'IPD', 'is_clinical': True},
            {'name': 'Emergency Department', 'code': 'ER', 'is_clinical': True},
            {'name': 'Pharmacy', 'code': 'PHARM', 'is_clinical': False},
            {'name': 'Laboratory', 'code': 'LAB', 'is_clinical': False},
            {'name': 'Radiology', 'code': 'RAD', 'is_clinical': False},
            {'name': 'Billing', 'code': 'BILL', 'is_clinical': False},
            {'name': 'Human Resources', 'code': 'HR', 'is_clinical': False},
        ]
        
        for dept_data in default_departments:
            Department.objects.create(tenant=tenant, **dept_data)


class TenantUserSerializer(serializers.ModelSerializer):
    """Serializer for tenant users."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    tenant_code = serializers.CharField(source='tenant.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    state_name = serializers.CharField(source='state.name', read_only=True)
    full_name = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)
    employee_id = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = TenantUser
        exclude = ('tenant', 'username')
        read_only_fields = [
            'created_at', 'updated_at', 'last_login',
            'last_login_ip', 'password_changed_at',
            'failed_login_attempts', 'account_locked_until'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': True},
        }
    
    def get_full_name(self, obj):
        return obj.get_full_name()

    def _resolve_tenant(self):
        tenant = self.context.get('tenant')
        if tenant:
            return tenant

        request = self.context.get('request')
        if not request:
            return None

        # 1) Normal request user context
        user = getattr(request, 'user', None)
        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                return tenant

            tenant_user = getattr(user, 'tenant_user', None)
            if tenant_user and getattr(tenant_user, 'tenant', None):
                return tenant_user.tenant

            tenant_public_id = getattr(user, 'tenant_public_id', None)
            if tenant_public_id:
                tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                if tenant:
                    return tenant

            tenant_id = getattr(user, 'tenant_id', None)
            if tenant_id:
                tenant = Tenant.objects.filter(public_id=tenant_id).first()
                if tenant is None and str(tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(tenant_id)).first()
                if tenant:
                    return tenant

        # 2) Fallback: decode JWT claims directly from the Authorization header.
        auth_header = request.META.get('HTTP_AUTHORIZATION', '') if request else ''
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.SIMPLE_JWT['SIGNING_KEY'],
                    algorithms=['HS256'],
                    options={'verify_exp': False}
                )
                tenant_public_id = payload.get('tenant_public_id') or payload.get('tenant_id')
                if tenant_public_id:
                    tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                    if tenant is None and str(tenant_public_id).isdigit():
                        tenant = Tenant.objects.filter(id=int(tenant_public_id)).first()
                    if tenant:
                        return tenant
            except Exception:
                pass

        return None

    def validate(self, attrs):
        tenant = self._resolve_tenant()
        if tenant:
            attrs['tenant'] = tenant
        elif 'tenant' in attrs and not attrs.get('tenant'):
            attrs.pop('tenant')

        # Make phone optional for admin-created staff accounts.
        attrs.setdefault('phone', '')

        # If a username is not supplied, allow the model to generate one.
        if attrs.get('username') == '':
            attrs.pop('username')

        # Do not block creation here if tenant will be inferred from request context.
        # The create() method will still enforce this if needed.
        return attrs
    
    def validate_email(self, value):
        """Validate email format and uniqueness within tenant."""
        try:
            validate_email(value)
        except:
            raise serializers.ValidationError("Invalid email format")
        
        # Check uniqueness within tenant
        tenant = self._resolve_tenant()
        if tenant:
            if TenantUser.objects.filter(tenant=tenant, email=value).exists():
                raise serializers.ValidationError("Email already exists in this tenant")
        
        return value.lower()
    
    def validate_username(self, value):
        """Validate username uniqueness within tenant."""
        tenant = self._resolve_tenant()
        if tenant:
            if TenantUser.objects.filter(tenant=tenant, username=value).exists():
                raise serializers.ValidationError("Username already exists in this tenant")
        return value
    
    def validate_password(self, value):
        """Validate password strength."""
        if value:
            validate_password(value)
        return value
    
    def create(self, validated_data):
        # Get tenant from context or infer from the authenticated request user.
        tenant = self._resolve_tenant()
        if not tenant and 'tenant' in validated_data:
            tenant = validated_data.get('tenant')

        if not tenant:
            raise serializers.ValidationError({"tenant": ["This field is required."]})

        # Remove tenant from validated_data if present (to avoid duplicate)
        validated_data.pop('tenant', None)
        
        # Extract password
        password = validated_data.pop('password', None)

        # Make phone optional and normalize empty strings.
        validated_data['phone'] = validated_data.get('phone') or ''

        # Ensure username can be generated if omitted.
        if not validated_data.get('username'):
            validated_data['username'] = ''

        # If caller does not supply a username, let the model auto-generate one
        # from the generated employee_id.
        if not validated_data.get('employee_id'):
            validated_data['employee_id'] = None
        
        # Create user
        user = TenantUser.objects.create(tenant=tenant, **validated_data)
        
        # Set password if provided
        if password:
            user.set_password(password)
            user.save()
        
        return user
    
    def update(self, instance, validated_data):
        # Handle password update
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance

class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for departments."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    head_name = serializers.CharField(source='head.get_full_name', read_only=True)
    
    class Meta:
        model = Department
        # Exclude tenant and let it be set in validate/create
        exclude = ('tenant',)
        read_only_fields = ['created_at', 'updated_at']

    def _resolve_tenant(self):
        """Resolve tenant from context or request - identical to TenantUserSerializer."""
        tenant = self.context.get('tenant')
        if tenant:
            return tenant

        request = self.context.get('request')
        if not request:
            return None

        # 1) Normal request user context
        user = getattr(request, 'user', None)
        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                return tenant

            tenant_user = getattr(user, 'tenant_user', None)
            if tenant_user and getattr(tenant_user, 'tenant', None):
                return tenant_user.tenant

            tenant_public_id = getattr(user, 'tenant_public_id', None)
            if tenant_public_id:
                tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                if tenant:
                    return tenant

            tenant_id = getattr(user, 'tenant_id', None)
            if tenant_id:
                tenant = Tenant.objects.filter(public_id=tenant_id).first()
                if tenant is None and str(tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(tenant_id)).first()
                if tenant:
                    return tenant

        # 2) Fallback: decode JWT claims directly from the Authorization header.
        auth_header = request.META.get('HTTP_AUTHORIZATION', '') if request else ''
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.SIMPLE_JWT['SIGNING_KEY'],
                    algorithms=['HS256'],
                    options={'verify_exp': False}
                )
                tenant_public_id = payload.get('tenant_public_id') or payload.get('tenant_id')
                if tenant_public_id:
                    tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                    if tenant is None and str(tenant_public_id).isdigit():
                        tenant = Tenant.objects.filter(id=int(tenant_public_id)).first()
                    if tenant:
                        return tenant
            except Exception:
                pass

        return None

    def validate(self, attrs):
        """Validate and set tenant from context."""
        tenant = self._resolve_tenant()
        if not tenant:
            raise serializers.ValidationError({"tenant": ["This field is required."]})
        
        attrs['tenant'] = tenant
        return attrs
    
    def create(self, validated_data):
        """Create department with tenant from context."""
        tenant = validated_data.get('tenant')
        if not tenant:
            tenant = self._resolve_tenant()
            if not tenant:
                raise serializers.ValidationError({"tenant": ["This field is required."]})
            validated_data['tenant'] = tenant
        
        return super().create(validated_data)
    
    

class TenantSettingSerializer(serializers.ModelSerializer):
    """Serializer for tenant settings."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    
    class Meta:
        model = TenantSetting
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def validate_tax_rate(self, value):
        """Validate tax rate (0-100%)."""
        if value < 0 or value > 100:
            raise serializers.ValidationError("Tax rate must be between 0 and 100")
        return value
    
    def validate_session_timeout(self, value):
        """Validate session timeout (5-1440 minutes)."""
        if value < 5 or value > 1440:
            raise serializers.ValidationError("Session timeout must be between 5 and 1440 minutes")
        return value


class TenantModuleSerializer(serializers.ModelSerializer):
    """Serializer for tenant modules."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    
    class Meta:
        model = TenantModule
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TenantInvitationSerializer(serializers.ModelSerializer):
    """Serializer for tenant invitations."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = TenantInvitation
        fields = '__all__'
        read_only_fields = [
            'created_at', 'updated_at', 'token',
            'sent_at', 'accepted_at', 'status'
        ]
    
    def validate_email(self, value):
        """Validate email and check if already a user."""
        try:
            validate_email(value)
        except:
            raise serializers.ValidationError("Invalid email format")
        
        # Check if user already exists in tenant
        tenant = self.context.get('tenant')
        if tenant and TenantUser.objects.filter(tenant=tenant, email=value).exists():
            raise serializers.ValidationError("User with this email already exists in the tenant")
        
        # Check for pending invitation
        if tenant:
            pending_invite = TenantInvitation.objects.filter(
                tenant=tenant,
                email=value,
                status=TenantInvitation.InvitationStatus.PENDING
            ).exists()
            if pending_invite:
                raise serializers.ValidationError("Pending invitation already exists for this email")
        
        return value.lower()


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting tenant invitations."""
    token = serializers.CharField(required=True)
    username = serializers.CharField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        # Check if passwords match
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})
        
        # Validate password strength
        validate_password(data['password'])
        
        # Check invitation
        token = data['token']
        try:
            invitation = TenantInvitation.objects.get(
                token=token,
                status=TenantInvitation.InvitationStatus.PENDING
            )
        except TenantInvitation.DoesNotExist:
            raise serializers.ValidationError({"token": "Invalid or expired invitation"})
        
        if invitation.is_expired():
            invitation.status = TenantInvitation.InvitationStatus.EXPIRED
            invitation.save()
            raise serializers.ValidationError({"token": "Invitation has expired"})
        
        data['invitation'] = invitation
        return data
    
    def save(self, **kwargs):
        invitation = self.validated_data['invitation']
        
        # Create user from invitation
        user_data = {
            'username': self.validated_data['username'],
            'first_name': self.validated_data['first_name'],
            'last_name': self.validated_data['last_name'],
            'password': self.validated_data['password'],
        }
        
        return invitation.accept(user_data)


class TenantActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for tenant activity logs."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    
    class Meta:
        model = TenantActivityLog
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TenantBackupSerializer(serializers.ModelSerializer):
    """Serializer for tenant backups."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = TenantBackup
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return None


class TenantSummarySerializer(serializers.ModelSerializer):
    """Serializer for tenant summary statistics."""
    user_count = serializers.IntegerField(read_only=True)
    patient_count = serializers.IntegerField(read_only=True)
    department_count = serializers.IntegerField(read_only=True)
    active_modules_count = serializers.IntegerField(read_only=True)
    storage_used_mb = serializers.FloatField(read_only=True)
    last_backup_time = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'code', 'domain', 'subscription_status',
            'subscription_plan', 'user_count', 'patient_count',
            'department_count', 'active_modules_count',
            'storage_used_mb', 'last_backup_time'
        ]