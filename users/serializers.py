from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
import pyotp
import base64
import hashlib

from .models import GlobalUser, User2FA, RSAKey, UserSession, SecurityEvent, UserNotification
from core.models import AuditLog


class GlobalUserSerializer(serializers.ModelSerializer):
    """Serializer for GlobalUser model."""
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = GlobalUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'employee_id', 'phone', 'is_active', 'is_staff',
            'date_joined', 'last_login', 'two_fa_enabled', 'two_fa_method',
            'last_login_ip', 'can_create_tenants', 'can_suspend_tenants',
            'can_delete_tenants', 'can_view_all_tenants', 'password', 'confirm_password'
        ]
        read_only_fields = [
            'id', 'date_joined', 'last_login', 'last_login_ip',
            'is_active', 'is_staff', 'is_superuser'
        ]
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()
    
    def validate(self, data):
        # Check if password and confirm_password match
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Validate email
        if 'email' in data:
            try:
                validate_email(data['email'])
            except:
                raise serializers.ValidationError({"email": "Enter a valid email address."})
        
        # Validate password strength
        if password:
            try:
                validate_password(password)
            except Exception as e:
                raise serializers.ValidationError({"password": list(e)})
        
        return data
    
    def create(self, validated_data):
        # Remove confirm_password before creating user
        validated_data.pop('confirm_password', None)
        
        password = validated_data.pop('password', None)
        user = GlobalUser(**validated_data)
        
        if password:
            user.set_password(password)
        
        user.save()
        return user
    
    def update(self, instance, validated_data):
        # Handle password update
        password = validated_data.pop('password', None)
        validated_data.pop('confirm_password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
            instance.password_changed_at = timezone.now()
        
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    username = serializers.CharField(required=False)
    identifier = serializers.CharField(required=False)
    user_id = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True, required=True)
    device_id = serializers.CharField(required=False)
    rsa_signature = serializers.CharField(required=False)
    
    def validate(self, data):
        username = data.get('username') or data.get('identifier') or data.get('user_id')
        password = data.get('password')

        if not username:
            raise serializers.ValidationError({"user_id": "This field is required."})
        
        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if not user:
            raise serializers.ValidationError("Invalid user ID, username, employee ID, or password.")
        
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        
        if user.is_account_locked():
            raise serializers.ValidationError("Account is locked. Please contact administrator.")
        
        data['user'] = user
        return data


class TwoFASerializer(serializers.Serializer):
    """Serializer for 2FA verification."""
    user_id = serializers.IntegerField(required=True)
    code = serializers.CharField(required=True)
    method = serializers.ChoiceField(choices=User2FA.TwoFAMethod.choices)
    device_id = serializers.CharField(required=False)
    
    def validate(self, data):
        user_id = data.get('user_id')
        code = data.get('code')
        method = data.get('method')
        
        try:
            user = GlobalUser.objects.get(id=user_id)
        except GlobalUser.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        
        # Check if user has 2FA enabled
        if not user.two_fa_enabled:
            raise serializers.ValidationError("2FA is not enabled for this user.")
        
        # Get or create 2FA settings
        two_fa_settings, created = User2FA.objects.get_or_create(user=user)
        
        # Verify code based on method
        if method == User2FA.TwoFAMethod.TOTP:
            if not two_fa_settings.totp_secret:
                raise serializers.ValidationError("TOTP not set up for this user.")
            
            totp = pyotp.TOTP(two_fa_settings.totp_secret)
            if not totp.verify(code):
                raise serializers.ValidationError("Invalid TOTP code.")
        
        elif method == User2FA.TwoFAMethod.SMS:
            # SMS verification logic (simplified)
            # In production, implement proper SMS verification
            if not two_fa_settings.sms_verified:
                raise serializers.ValidationError("SMS not verified for this user.")
        
        elif method == User2FA.TwoFAMethod.EMAIL:
            # Email verification logic (simplified)
            if not two_fa_settings.email_verified:
                raise serializers.ValidationError("Email not verified for this user.")
        
        data['user'] = user
        data['two_fa_settings'] = two_fa_settings
        return data


class RSASerializer(serializers.ModelSerializer):
    """Serializer for RSA keys."""
    class Meta:
        model = RSAKey
        fields = [
            'id', 'key_name', 'key_fingerprint', 'key_size',
            'created_at', 'expires_at', 'is_primary', 'key_usage',
            'algorithm', 'last_used', 'usage_count'
        ]
        read_only_fields = [
            'id', 'key_fingerprint', 'created_at', 'expires_at',
            'last_used', 'usage_count'
        ]


class RSAKeyGenerationSerializer(serializers.Serializer):
    """Serializer for RSA key generation."""
    key_name = serializers.CharField(required=True)
    key_size = serializers.IntegerField(default=2048, min_value=1024, max_value=4096)
    expires_in_days = serializers.IntegerField(default=365, min_value=30, max_value=3650)
    is_primary = serializers.BooleanField(default=False)
    key_usage = serializers.ListField(
        child=serializers.ChoiceField(choices=['sign', 'encrypt', 'verify']),
        default=['sign']
    )


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        # Check if new passwords match
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Validate new password strength
        try:
            validate_password(new_password)
        except Exception as e:
            raise serializers.ValidationError({"new_password": list(e)})
        
        # Check if old password is correct
        user = self.context['request'].user
        if not user.check_password(old_password):
            raise serializers.ValidationError({"old_password": "Current password is incorrect."})
        
        # Check if new password is same as old
        if old_password == new_password:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})
        
        return data


class UserSessionSerializer(serializers.ModelSerializer):
    """Serializer for user sessions."""
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserSession
        fields = [
            'id', 'session_key', 'ip_address', 'user_agent',
            'device_info', 'location_info', 'last_activity',
            'expires_at', 'is_active', 'requires_reauth',
            'is_trusted_device', 'user_username'
        ]
        read_only_fields = ['id', 'session_key', 'created_at', 'last_activity']


class SecurityEventSerializer(serializers.ModelSerializer):
    """Serializer for security events."""
    user_username = serializers.CharField(source='user.username', read_only=True, allow_null=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = SecurityEvent
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class UserNotificationSerializer(serializers.ModelSerializer):
    """Serializer for user notifications."""
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserNotification
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Add human-readable time difference
        from django.utils.timesince import timesince
        data['time_since'] = timesince(instance.created_at)
        return data


class TOTPSetupSerializer(serializers.Serializer):
    """Serializer for TOTP setup."""
    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)
    qr_code = serializers.CharField(read_only=True)
    
    def create(self, validated_data):
        user = self.context['user']
        
        # Generate TOTP secret
        secret = pyotp.random_base32()
        
        # Create provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="SmartCare HMS"
        )
        
        # Generate QR code (in production, use proper QR code generation)
        qr_code = f"otpauth://totp/SmartCare%20HMS:{user.email}?secret={secret}&issuer=SmartCare%20HMS"
        
        # Save secret to user's 2FA settings
        two_fa_settings, created = User2FA.objects.get_or_create(user=user)
        two_fa_settings.totp_secret = secret
        two_fa_settings.method = User2FA.TwoFAMethod.TOTP
        two_fa_settings.save()
        
        return {
            'secret': secret,
            'provisioning_uri': provisioning_uri,
            'qr_code': qr_code
        }


class BackupCodeSerializer(serializers.Serializer):
    """Serializer for backup code generation."""
    codes = serializers.ListField(child=serializers.CharField(), read_only=True)
    generated_at = serializers.DateTimeField(read_only=True)
    
    def create(self, validated_data):
        user = self.context['user']
        count = validated_data.get('count', 10)
        
        # Get or create 2FA settings
        two_fa_settings, created = User2FA.objects.get_or_create(user=user)
        
        # Generate backup codes
        codes = two_fa_settings.generate_backup_codes(count)
        
        return {
            'codes': codes,
            'generated_at': two_fa_settings.backup_codes_generated_at
        }