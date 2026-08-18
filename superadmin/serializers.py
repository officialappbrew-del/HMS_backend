from rest_framework import serializers
from tenants.models import Tenant, TenantUser, SupportTicket
from users.models import GlobalUser
from core.models import AuditLog


class TenantAdminListSerializer(serializers.ModelSerializer):
    """Serializer for listing tenants in the super admin dashboard."""
    subscription_plan_name = serializers.CharField(
        source='subscription_plan.name', read_only=True, default=None
    )
    user_count = serializers.IntegerField(read_only=True)
    state_name = serializers.CharField(source='state.name', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    root_admin = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            'public_id', 'name', 'code', 'domain', 'email', 'phone',
            'is_active', 'subscription_status', 'subscription_plan',
            'subscription_plan_name', 'monthly_fee', 'subscription_start_date',
            'subscription_end_date', 'facility_type', 'state_name',
            'country_name', 'user_count', 'created_at', 'root_admin',
        ]

    def get_root_admin(self, obj):
        root_admins = self.context.get('root_admins') or {}
        admin = root_admins.get(obj.id)
        if not admin:
            return None
        return {
            'id': admin.id,
            'name': admin.get_full_name() or admin.username,
            'email': admin.email,
            'phone': admin.phone,
            'role': admin.role,
            'employee_id': admin.employee_id,
        }


class TenantDetailSerializer(serializers.ModelSerializer):
    """Serializer for retrieving a single tenant's full details (super admin).

    Expands the list serializer so the detail modal can show all tenant
    information including nested reference details for facility type,
    subscription plan, state and LGA.
    """
    state_details = serializers.SerializerMethodField()
    lga_details = serializers.SerializerMethodField()
    tenant_id = serializers.SerializerMethodField()
    country_name = serializers.CharField(source='country.name', read_only=True, default=None)
    facility_type_details = serializers.SerializerMethodField()
    subscription_plan_details = serializers.SerializerMethodField()
    days_remaining_in_trial = serializers.SerializerMethodField()
    is_active_status = serializers.SerializerMethodField()
    root_admin = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            'tenant_id', 'state_details', 'lga_details', 'country_name',
            'facility_type_details', 'subscription_plan_details',
            'subscription_start_date', 'subscription_end_date',
            'nhis_accreditation_date', 'nhis_expiry_date', 'established_date',
            'is_active_status', 'days_remaining_in_trial', 'created_at',
            'updated_at', 'name', 'code', 'domain', 'schema_name',
            'public_id', 'is_active', 'email', 'phone', 'phone2', 'address',
            'city', 'registration_number', 'tax_id', 'website',
            'subscription_status', 'monthly_fee', 'payment_method',
            'billing_email', 'nhis_accreditation', 'nhis_provider_id',
            'bed_capacity', 'operating_hours', 'emergency_services',
            'config', 'features', 'notes', 'logo', 'state', 'lga',
            'country', 'facility_type', 'subscription_plan', 'created_by',
            'root_admin',
        ]

    def get_root_admin(self, obj):
        admin = getattr(obj, '_root_admin', None)
        if not admin:
            return None
        return {
            'id': admin.id,
            'name': admin.get_full_name() or admin.username,
            'email': admin.email,
            'phone': admin.phone,
            'role': admin.role,
            'employee_id': admin.employee_id,
        }

    def get_tenant_id(self, obj):
        return str(obj.public_id)

    def get_state_details(self, obj):
        if obj.state_id:
            return {
                'id': obj.state.id,
                'name': obj.state.name,
                'code': getattr(obj.state, 'code', None),
            }
        return None

    def get_lga_details(self, obj):
        if obj.lga_id:
            return {
                'id': obj.lga.id,
                'name': obj.lga.name,
                'code': getattr(obj.lga, 'code', None),
            }
        return None

    def get_facility_type_details(self, obj):
        if obj.facility_type_id:
            return {
                'id': obj.facility_type.id,
                'name': obj.facility_type.name,
                'description': getattr(obj.facility_type, 'description', None),
                'code': getattr(obj.facility_type, 'code', None),
            }
        return None

    def get_subscription_plan_details(self, obj):
        plan = obj.subscription_plan
        if not plan:
            return None
        return {
            'id': plan.id,
            'name': plan.name,
            'code': plan.code,
            'description': plan.description,
            'price_monthly': plan.price_monthly,
            'price_quarterly': plan.price_quarterly,
            'price_yearly': plan.price_yearly,
            'currency': plan.currency,
            'max_users': plan.max_users,
            'max_patients': plan.max_patients,
            'max_storage_gb': plan.max_storage_gb,
            'max_api_calls_per_day': plan.max_api_calls_per_day,
            'email_limit_monthly': plan.email_limit_monthly,
            'sms_limit_monthly': plan.sms_limit_monthly,
            'is_default': plan.is_default,
            'is_active': plan.is_active,
        }

    def get_days_remaining_in_trial(self, obj):
        return obj.days_remaining_in_trial()

    def get_is_active_status(self, obj):
        return obj.is_active


class TenantUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a tenant from the super admin dashboard."""

    class Meta:
        model = Tenant
        fields = [
            'name', 'email', 'phone', 'phone2', 'address', 'city',
            'state', 'lga', 'country', 'facility_type', 'registration_number',
            'tax_id', 'website', 'subscription_plan', 'subscription_status',
            'subscription_start_date', 'subscription_end_date', 'monthly_fee',
            'payment_method', 'billing_email', 'nhis_accreditation',
            'nhis_provider_id', 'nhis_accreditation_date', 'nhis_expiry_date',
            'bed_capacity', 'established_date', 'emergency_services', 'notes',
        ]
        extra_kwargs = {
            'name': {'required': False},
            'email': {'required': False},
            'phone': {'required': False},
            'address': {'required': False},
            'city': {'required': False},
            'facility_type': {'required': False},
            'registration_number': {'required': False},
        }

    def validate_domain(self, value):
        return value

    def validate_registration_number(self, value):
        return value.upper()

    def validate_nhis_provider_id(self, value):
        if value == '':
            return None
        return value


class TenantCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a tenant from the super admin dashboard."""
    root_admin = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Tenant
        fields = [
            'name', 'code', 'domain', 'schema_name', 'email', 'phone',
            'address', 'city', 'state', 'lga', 'country', 'facility_type',
            'registration_number', 'tax_id', 'website', 'subscription_plan',
            'subscription_status', 'monthly_fee', 'bed_capacity',
            'is_active', 'notes', 'root_admin',
        ]
        read_only_fields = ['code', 'schema_name']

    def validate_domain(self, value):
        import re
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
        if not re.match(domain_pattern, value):
            raise serializers.ValidationError('Invalid domain format')
        return value.lower()

    def validate_registration_number(self, value):
        return value.upper()

    def validate_nhis_provider_id(self, value):
        if value == '':
            return None
        return value

    def create(self, validated_data):
        validated_data.pop('root_admin', None)
        return Tenant.objects.create(**validated_data)


class PlatformUserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users across all tenants in super admin dashboard."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    tenant_code = serializers.CharField(source='tenant.code', read_only=True)
    tenant_domain = serializers.CharField(source='tenant.domain', read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = TenantUser
        fields = [
            'id', 'employee_id', 'username', 'email', 'first_name',
            'last_name', 'full_name', 'role', 'is_active', 'is_root_admin',
            'tenant_name', 'tenant_code', 'tenant_domain', 'last_login',
            'created_at',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for platform-wide audit logs."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True, default=None)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id', 'tenant', 'tenant_name', 'user', 'user_name', 'action',
            'resource_type', 'resource_id', 'severity', 'title', 'actor',
            'ip_address', 'is_verified', 'timestamp',
        ]

    def get_user_name(self, obj):
        if obj.user:
            return getattr(obj.user, 'username', '') or ''
        return obj.actor or ''


class SupportTicketSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True, default=None)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'tenant', 'tenant_name', 'subject', 'description',
            'priority', 'status', 'created_by_name', 'created_by_email',
            'created_by_role', 'assigned_to', 'assigned_to_name',
            'resolved_at', 'resolution_notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GlobalAdminSerializer(serializers.ModelSerializer):
    employee_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = GlobalUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'role_label', 'employee_id', 'phone', 'is_active',
            'is_superuser', 'can_create_tenants', 'can_suspend_tenants',
            'can_delete_tenants', 'can_view_all_tenants',
            'can_manage_admin_permissions', 'notes', 'created_by', 'date_joined',
        ]
        read_only_fields = ['id', 'date_joined']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def get_role_label(self, obj):
        if getattr(obj, 'is_superuser', False):
            return 'Super Admin'
        return obj.get_role_display()

    def validate_employee_id(self, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def create(self, validated_data):
        if 'employee_id' in validated_data:
            validated_data['employee_id'] = self.validate_employee_id(validated_data['employee_id'])
        password = self.initial_data.get('password', '')
        user = GlobalUser(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = self.initial_data.get('password', '')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
