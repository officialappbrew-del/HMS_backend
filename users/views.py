from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login, logout, authenticate
from django.core.cache import cache
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q as models_Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
import pyotp
import qrcode
import base64
import uuid
import secrets
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

from smartcare_hms.throttling import AuthenticationThrottle
from .models import (
    GlobalUser, User2FA, RSAKey, UserSession,
    SecurityEvent, UserNotification, PasswordResetToken
)
from .serializers import (
    GlobalUserSerializer, LoginSerializer, TwoFASerializer,
    RSASerializer, RSAKeyGenerationSerializer, PasswordChangeSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    PasswordResetVerifySerializer,
    UserSessionSerializer, SecurityEventSerializer,
    UserNotificationSerializer, TOTPSetupSerializer, BackupCodeSerializer
)
from core.permissions import IsSystemAdmin
from core.models import AuditLog
from tenants.models import Tenant, TenantUser
from patients.models import Patient
from patients.serializers import PatientLoginSerializer
from .tasks import queue_login_notification


def _tenant_requires_2fa(tenant):
    from tenants.models import TenantSetting
    return TenantSetting.objects.filter(tenant=tenant, require_2fa=True).exists()


def _start_tenant_email_2fa(tenant, user):
    from tenants.communication import send_tenant_email

    code = f'{secrets.randbelow(1000000):06d}'
    challenge_id = uuid.uuid4().hex
    cache.set(
        f'tenant-2fa:{challenge_id}',
        {'code': code, 'tenant_id': str(tenant.public_id), 'user_id': user.id},
        600,
    )
    send_tenant_email(
        tenant=tenant,
        subject=f'{tenant.name} sign-in verification code',
        message=f'Your sign-in verification code is {code}. It expires in 10 minutes.',
        recipient_list=[user.email],
        fail_silently=False,
    )
    return challenge_id


def _set_auth_cookies(response, access_token, refresh_token=None):
    """Set HttpOnly, Secure, SameSite=Strict cookies for access and refresh tokens."""
    if access_token:
        response.set_cookie(
            key='access_token',
            value=access_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite='Strict',
            max_age=30 * 60,  # 30 minutes
            path='/',
        )
    if refresh_token:
        response.set_cookie(
            key='refresh_token',
            value=refresh_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite='Strict',
            max_age=7 * 24 * 60 * 60,  # 7 days
            path='/',
        )


def _clear_auth_cookies(response):
    """Delete auth cookies on logout."""
    for key in ('access_token', 'refresh_token'):
        response.delete_cookie(key, path='/')


def _get_client_ip(request):
    """Return a valid IP address string for audit logging.

    Some requests, especially local/test or proxied traffic, may not provide a
    REMOTE_ADDR value. We must never persist NULL for a required GenericIPAddress
    field, so we fall back to a safe loopback address instead of crashing.
    """
    value = getattr(request, 'user_ip', None)
    if value:
        return value

    meta = getattr(request, 'META', {}) or {}
    forwarded = meta.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        first_ip = forwarded.split(',')[0].strip()
        if first_ip:
            return first_ip

    remote_addr = meta.get('REMOTE_ADDR') or meta.get('HTTP_X_REAL_IP')
    if remote_addr:
        return remote_addr

    return '127.0.0.1'


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for managing global users."""
    queryset = GlobalUser.objects.all()
    serializer_class = GlobalUserSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsSystemAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        user = self.request.user
        
        # System admins can see all users
        if user.is_superuser or user.role == 'super_admin':
            return GlobalUser.objects.all()
        
        # System admins can see all users
        if user.role == 'system_admin':
            return GlobalUser.objects.all()
        
        # Support staff can see active users
        if user.role == 'support':
            return GlobalUser.objects.filter(is_active=True)
        
        # Auditors can see active users
        if user.role == 'auditor':
            return GlobalUser.objects.filter(is_active=True)
        
        # Regular users can only see themselves
        return GlobalUser.objects.filter(id=user.id)
    
    def perform_create(self, serializer):
        user = serializer.save(created_by=self.request.user)
        
        # Log the action
        AuditLog.objects.create(
            user=self.request.user,
            action='create_user',
            resource_type='user',
            resource_id=str(user.id),
            new_values=serializer.data
        )
        
        # Create security event
        SecurityEvent.objects.create(
            user=self.request.user,
            event_type=SecurityEvent.EventType.ACCOUNT_CREATED,
            severity=SecurityEvent.Severity.INFO,
            description=f'User {user.username} created by {self.request.user.username}',
            ip_address=self.get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', '')
        )
    
    def perform_update(self, serializer):
        old_user = self.get_object()
        old_data = GlobalUserSerializer(old_user).data
        
        user = serializer.save()
        
        # Log the action
        AuditLog.objects.create(
            user=self.request.user,
            action='update_user',
            resource_type='user',
            resource_id=str(user.id),
            old_values=old_data,
            new_values=serializer.data
        )
    
    def perform_destroy(self, instance):
        user_id = instance.id
        username = instance.username
        
        # Log before deletion
        AuditLog.objects.create(
            user=self.request.user,
            action='delete_user',
            resource_type='user',
            resource_id=str(user_id),
            old_values={'username': username}
        )
        
        instance.delete()
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's profile."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change current user's password."""
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.password_changed_at = timezone.now()
            # Bump token_version to invalidate all previously issued JWTs.
            user.token_version += 1
            user.save()
            
            if isinstance(user, GlobalUser):
                SecurityEvent.objects.create(
                    user=user,
                    event_type=SecurityEvent.EventType.PASSWORD_CHANGE,
                    severity=SecurityEvent.Severity.INFO,
                    description='Password changed successfully',
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            
            # Terminate all other sessions
            UserSession.objects.filter(
                user=user,
                is_active=True
            ).exclude(
                session_key=request.session.session_key
            ).update(is_active=False)
            
            return Response({'detail': 'Password changed successfully'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def lock_account(self, request, pk=None):
        """Lock user account."""
        user = self.get_object()
        duration = request.data.get('duration_minutes', 30)
        
        user.lock_account(duration)
        
        if isinstance(user, GlobalUser):
            SecurityEvent.objects.create(
                user=user,
                event_type=SecurityEvent.EventType.ACCOUNT_LOCKED,
                severity=SecurityEvent.Severity.HIGH,
                description=f'Account locked for {duration} minutes',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                metadata={'duration_minutes': duration}
            )
        
        return Response({'detail': f'Account locked for {duration} minutes'})
    
    @action(detail=True, methods=['post'])
    def unlock_account(self, request, pk=None):
        """Unlock user account."""
        user = self.get_object()
        user.unlock_account()
        
        if isinstance(user, GlobalUser):
            SecurityEvent.objects.create(
                user=user,
                event_type=SecurityEvent.EventType.ACCOUNT_UNLOCKED,
                severity=SecurityEvent.Severity.INFO,
                description='Account unlocked',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        
        return Response({'detail': 'Account unlocked'})
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# class AuthenticationView(APIView):
#     """Handle user authentication."""
#     permission_classes = [permissions.AllowAny]
    
#     def post(self, request):
#         serializer = LoginSerializer(data=request.data)
        
#         if serializer.is_valid():
#             user = serializer.validated_data['user']
            
#             # Record successful login attempt
#             user.record_login_attempt(
#                 ip_address=self.get_client_ip(request),
#                 successful=True
#             )
            
#             # Check if 2FA is required
#             if user.two_fa_enabled:
#                 # Generate 2FA verification token
#                 refresh = RefreshToken.for_user(user)
#                 refresh['two_fa_required'] = True
#                 refresh['two_fa_verified'] = False
                
#                 return Response({
#                     'requires_2fa': True,
#                     'user_id': user.id,
#                     'access_token': str(refresh.access_token),
#                     'refresh_token': str(refresh),
#                     'two_fa_methods': self.get_available_2fa_methods(user)
#                 })
            
#             # No 2FA required, complete login
#             return self.complete_login(user, request)
        
#         # Record failed login attempt
#         username = request.data.get('username')
#         try:
#             user = GlobalUser.objects.get(username=username)
#             user.record_login_attempt(
#                 ip_address=self.get_client_ip(request),
#                 successful=False
#             )
#         except GlobalUser.DoesNotExist:
#             pass
        
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     def complete_login(self, user, request):
#         """Complete login process."""
#         # Create user session
#         session = UserSession.objects.create(
#             user=user,
#             session_key=request.session.session_key,
#             ip_address=self.get_client_ip(request),
#             user_agent=request.META.get('HTTP_USER_AGENT', ''),
#             expires_at=timezone.now() + timezone.timedelta(hours=1),
#             device_info=self.get_device_info(request)
#         )
        
#         # Generate JWT tokens
#         refresh = RefreshToken.for_user(user)
#         refresh['session_id'] = session.session_key
#         refresh['two_fa_verified'] = True
        
#         # Log security event
#         SecurityEvent.objects.create(
#             user=user,
#             event_type=SecurityEvent.EventType.LOGIN_SUCCESS,
#             severity=SecurityEvent.Severity.INFO,
#             description='Login successful',
#             ip_address=self.get_client_ip(request),
#             user_agent=request.META.get('HTTP_USER_AGENT', '')
#         )
        
#         return Response({
#             'user': GlobalUserSerializer(user).data,
#             'access_token': str(refresh.access_token),
#             'refresh_token': str(refresh),
#             'session_id': session.session_key
#         })
    
#     def get_available_2fa_methods(self, user):
#         """Get available 2FA methods for user."""
#         try:
#             two_fa_settings = User2FA.objects.get(user=user)
#             return two_fa_settings.get_available_methods()
#         except User2FA.DoesNotExist:
#             return []
    
#     def get_device_info(self, request):
#         """Extract device information from request."""
#         user_agent = request.META.get('HTTP_USER_AGENT', '')
        
#         # Simple device detection (in production, use more sophisticated detection)
#         if 'Mobile' in user_agent:
#             device_type = 'mobile'
#         elif 'Tablet' in user_agent:
#             device_type = 'tablet'
#         else:
#             device_type = 'desktop'
        
#         return {
#             'device_type': device_type,
#             'user_agent': user_agent[:500]  # Limit length
#         }
    
#     def get_client_ip(self, request):
#         """Get client IP address."""
#         x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#         if x_forwarded_for:
#             ip = x_forwarded_for.split(',')[0]
#         else:
#             ip = request.META.get('REMOTE_ADDR')
#         return ip


# class TenantAuthenticationView(APIView):
#     """Handle tenant user authentication."""
#     permission_classes = [permissions.AllowAny]
    
#     def post(self, request):
#         # Get tenant from domain or query parameter
#         tenant_domain = request.data.get('tenant_domain') or request.GET.get('tenant')
        
#         if not tenant_domain:
#             return Response(
#                 {'error': 'Tenant domain is required'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         try:
#             # Get tenant
#             tenant = Tenant.objects.get(domain=tenant_domain, is_active=True)
#         except Tenant.DoesNotExist:
#             return Response(
#                 {'error': 'Tenant not found or inactive'},
#                 status=status.HTTP_404_NOT_FOUND
#             )
        
#         # Switch to tenant schema
#         from django.db import connection
#         connection.set_schema(tenant.schema_name)
        
#         try:
#             # Try to authenticate tenant user
#             serializer = LoginSerializer(data=request.data)
            
#             if serializer.is_valid():
#                 user = serializer.validated_data['user']
                
#                 # Create user session
#                 session = UserSession.objects.create(
#                     user=user,
#                     session_key=request.session.session_key,
#                     ip_address=self.get_client_ip(request),
#                     user_agent=request.META.get('HTTP_USER_AGENT', ''),
#                     expires_at=timezone.now() + timezone.timedelta(hours=1),
#                     device_info=self.get_device_info(request)
#                 )
                
#                 # Generate JWT tokens specific to tenant
#                 refresh = RefreshToken.for_user(user)
#                 refresh['tenant_id'] = tenant.id
#                 refresh['tenant_domain'] = tenant.domain
#                 refresh['tenant_schema'] = tenant.schema_name
#                 refresh['session_id'] = session.session_key
                
#                 # Switch back to public schema
#                 connection.set_schema('public')
                
#                 return Response({
#                     'tenant': {
#                         'id': tenant.id,
#                         'name': tenant.name,
#                         'domain': tenant.domain
#                     },
#                     'user': {
#                         'id': user.id,
#                         'username': user.username,
#                         'email': user.email,
#                         'role': user.role
#                     },
#                     'access_token': str(refresh.access_token),
#                     'refresh_token': str(refresh),
#                     'session_id': session.session_key
#                 })
            
#             # Switch back to public schema
#             connection.set_schema('public')
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
#         except Exception as e:
#             # Ensure we switch back to public schema on error
#             connection.set_schema('public')
#             return Response(
#                 {'error': str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
    
#     def get_client_ip(self, request):
#         x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#         if x_forwarded_for:
#             ip = x_forwarded_for.split(',')[0]
#         else:
#             ip = request.META.get('REMOTE_ADDR')
#         return ip
    
#     def get_device_info(self, request):
#         user_agent = request.META.get('HTTP_USER_AGENT', '')
        
#         if 'Mobile' in user_agent:
#             device_type = 'mobile'
#         elif 'Tablet' in user_agent:
#             device_type = 'tablet'
#         else:
#             device_type = 'desktop'
        
#         return {
#             'device_type': device_type,
#             'user_agent': user_agent[:500]
#         }

class AuthenticationView(APIView):
    """Handle both global and tenant user authentication."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthenticationThrottle]
    
    def post(self, request):
        data = request.data
        if isinstance(data, str):
            try:
                import json
                data = json.loads(data)
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Invalid JSON data. Please check your request body.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        tenant_domain = data.get('tenant_domain')
        tenant_id_from_body = data.get('tenant_id')
        tenant_id_from_header = request.headers.get('X-Tenant-ID')
        tenant_id = tenant_id_from_body or tenant_id_from_header

        if tenant_domain or tenant_id_from_body:
            logger.info(f"[AUTH] Routing to tenant auth: tenant_domain={tenant_domain} tenant_id={tenant_id_from_body}")
            return self.authenticate_tenant_user(data, request, tenant_domain, tenant_id_from_body)

        # An explicit user_id can identify a patient or tenant employee even
        # when the frontend also sends username/identifier aliases.
        if data.get('user_id') and data.get('password'):
            # Try patient authentication first
            patient_result = self.authenticate_patient_user(data, request)
            if patient_result:
                return patient_result
            # If patient auth fails, try tenant user auth
            logger.info(f"[AUTH] Patient auth failed, routing to tenant auth by user_id: user_id={data.get('user_id')}")
            return self.authenticate_tenant_user_by_user_id(data, request)

        logger.info(f"[AUTH] Routing to global auth: identifier={data.get('username') or data.get('identifier')}")
        return self.authenticate_global_user(data, request)
    
    def authenticate_tenant_user(self, data, request, tenant_domain=None, tenant_id=None):
        """Authenticate tenant user."""
        from django.db import connection
        
        # If tenant_id is provided instead of domain, look up the tenant
        if tenant_id and not tenant_domain:
            try:
                tenant = Tenant.objects.filter(public_id=tenant_id).first()
                if tenant is None and str(tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(tenant_id)).first()
                if tenant is None:
                    raise Tenant.DoesNotExist
                tenant_domain = tenant.domain
            except Tenant.DoesNotExist:
                return Response(
                    {'error': 'Tenant not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif tenant_domain:
            try:
                tenant = Tenant.objects.get(domain=tenant_domain)
            except Tenant.DoesNotExist:
                return Response(
                    {'error': 'Tenant not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {'error': 'Tenant domain or ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check tenant status
        if tenant.subscription_status not in {
            Tenant.SubscriptionStatus.ACTIVE,
            Tenant.SubscriptionStatus.TRIAL,
        }:
            return Response(
                {'error': 'Tenant is inactive'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Switch to tenant schema
        connection.set_schema(tenant.schema_name)

        try:
            identifier = data.get('user_id') or data.get('identifier') or data.get('username')
            password = data.get('password')

            if not identifier or not password:
                return Response(
                    {'error': 'user_id (or identifier/username) and password are required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = TenantUser.objects.filter(is_active=True, employee_id=identifier).first()
            if not user:
                user = TenantUser.objects.filter(is_active=True, username=identifier).first()
            if not user:
                return Response(
                    {'error': 'Invalid tenant credentials.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not user.check_password(password):
                return Response(
                    {'error': 'Invalid tenant credentials.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if _tenant_requires_2fa(tenant):
                try:
                    challenge_id = _start_tenant_email_2fa(tenant, user)
                except Exception:
                    logger.exception('Unable to send tenant 2FA code to %s', user.email)
                    return Response({'error': 'Unable to send the verification code.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                return Response({
                    'requires_2fa': True,
                    'tenant_2fa': True,
                    'challenge_id': challenge_id,
                    'tenant_id': str(tenant.public_id),
                    'tenant_user_id': user.id,
                    'message': 'A verification code was sent to your registered email address.',
                })

            queue_login_notification(
                recipient_email=user.email,
                user_name=user.get_full_name(),
                tenant_id=tenant.public_id,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )

            refresh = RefreshToken()
            refresh['user_id'] = user.id
            refresh['tenant_id'] = str(tenant.public_id)
            refresh['tenant_public_id'] = str(tenant.public_id)
            refresh['tenant_domain'] = tenant.domain
            refresh['is_tenant_user'] = True
            refresh['is_superadmin'] = bool(getattr(user, 'is_root_admin', False) or getattr(user, 'role', '') in ('super_admin', 'system_admin'))

            return Response({
                'message': 'Tenant login successful',
                'tenant': {
                    'public_id': str(tenant.public_id),
                    'name': tenant.name,
                    'domain': tenant.domain
                },
                'user': {
                    'id': user.id,
                    'user_id': user.employee_id or user.username,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'is_root_admin': user.is_root_admin,
                    'is_root_admin': user.is_root_admin,
                    'is_active': user.is_active,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name(),
                    'license_number': user.license_number,
                    'mdcn_number': user.mdcn_number,
                },
                'tokens': {
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                },
                'is_tenant_user': True
            })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            connection.set_schema('public')
    
    def authenticate_tenant_user_by_user_id(self, data, request):
        """Authenticate a tenant user using only user_id + password."""
        from django.db import connection

        user_id = data.get('user_id') or data.get('username') or data.get('identifier')
        password = data.get('password')

        if not user_id or not password:
            return Response(
                {'error': 'user_id and password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_domain = data.get('tenant_domain')
        explicit_tenant_id = data.get('tenant_id')
        header_tenant_id = request.headers.get('X-Tenant-ID')
        tenant = None

        if tenant_domain:
            tenant = Tenant.objects.filter(domain=tenant_domain).first()
        elif explicit_tenant_id:
            tenant = Tenant.objects.filter(public_id=explicit_tenant_id).first()
            if tenant is None and str(explicit_tenant_id).isdigit():
                tenant = Tenant.objects.filter(id=int(explicit_tenant_id)).first()
        else:
            # Employee IDs are tenant-scoped. Prefer their tenant prefix over
            # a stale X-Tenant-ID left in browser storage.
            tenant = self._resolve_tenant_from_identifier(user_id)
            if tenant is None and header_tenant_id:
                tenant = Tenant.objects.filter(public_id=header_tenant_id).first()
                if tenant is None and str(header_tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(header_tenant_id)).first()

        if tenant and tenant.subscription_status not in {
            Tenant.SubscriptionStatus.ACTIVE,
            Tenant.SubscriptionStatus.TRIAL,
        }:
            return Response(
                {'error': 'Tenant is inactive'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tenant:
            connection.set_schema(tenant.schema_name)
            try:
                user = TenantUser.objects.filter(is_active=True, employee_id=user_id).first()
                if not user:
                    user = TenantUser.objects.filter(is_active=True, username=user_id).first()
                if not user:
                    user = TenantUser.objects.filter(is_active=True, email=user_id).first()
                if user and user.check_password(password):
                    return self._build_tenant_login_response(tenant, user, 'employee_id' if user.employee_id == user_id else 'username' if user.username == user_id else 'email', request)
            finally:
                connection.set_schema('public')

            return Response(
                {'error': 'Invalid tenant credentials.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        active_tenants = list(
            Tenant.objects.filter(
                subscription_status__in=[
                    Tenant.SubscriptionStatus.ACTIVE,
                    Tenant.SubscriptionStatus.TRIAL,
                ]
            )
        )

        possible_matches = []

        for tenant in active_tenants:
            connection.set_schema(tenant.schema_name)
            try:
                user = TenantUser.objects.filter(is_active=True, employee_id=user_id).first()
                if not user:
                    user = TenantUser.objects.filter(is_active=True, username=user_id).first()
                if not user:
                    user = TenantUser.objects.filter(is_active=True, email=user_id).first()
                if user and user.check_password(password):
                    possible_matches.append((tenant, user, 'employee_id' if user.employee_id == user_id else 'username' if user.username == user_id else 'email'))
            finally:
                connection.set_schema('public')

        if len(possible_matches) == 1:
            matched_tenant, matched_user, matched_by = possible_matches[0]
            return self._build_tenant_login_response(matched_tenant, matched_user, matched_by, request)

        if len(possible_matches) > 1:
            # Attempt to disambiguate by matching the request host to a tenant domain.
            host = ''
            try:
                host = request.get_host().split(':')[0].lower()
            except Exception:
                host = (request.META.get('HTTP_HOST') or '').split(':')[0].lower()

            for t, u, m in possible_matches:
                if (t.domain or '').lower() == host and u and u.check_password(password):
                    return self._build_tenant_login_response(t, u, m, request)

            # Fallback: try Origin or Referer header to infer tenant domain
            origin = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER') or ''
            if origin:
                try:
                    from urllib.parse import urlparse
                    o_host = (urlparse(origin).hostname or '').lower()
                    for t, u, m in possible_matches:
                        if (t.domain or '').lower() == o_host and u and u.check_password(password):
                            return self._build_tenant_login_response(t, u, m, request)
                except Exception:
                    pass

            # Still ambiguous: return candidates and prompt client to provide tenant info
            return Response(
                {
                    'error': 'Ambiguous login. This identifier matches multiple tenants.',
                    'tenant_candidates': [
                        {
                            'public_id': str(t.public_id),
                            'name': t.name,
                            'domain': t.domain
                        }
                        for t, _, _ in possible_matches
                    ],
                    'message': 'Please include tenant_domain or X-Tenant-ID header to disambiguate.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'error': 'Invalid user ID or password.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def authenticate_patient_user(self, data, request):
        """Authenticate a patient using their identifier and password."""
        from django.db import connection

        identifier = str(data.get('user_id') or data.get('identifier') or '').strip()
        password = data.get('password')

        if not identifier or password is None:
            return None

        # Try to find the patient across all active tenants
        active_tenants = Tenant.objects.filter(
            subscription_status__in=[
                Tenant.SubscriptionStatus.ACTIVE,
                Tenant.SubscriptionStatus.TRIAL,
            ]
        )

        for tenant in active_tenants:
            connection.set_schema(tenant.schema_name)
            try:
                # Try to find patient by login_id, hospital_number, or mrn
                # MRN is the requested patient identifier; check it first
                # because legacy records can have overlapping login IDs.
                patient = Patient.objects.filter(mrn__iexact=identifier).first()

                if not patient:
                    patient = Patient.objects.filter(hospital_number__iexact=identifier).first()

                if not patient:
                    patient = Patient.objects.filter(login_id__iexact=identifier).first()

                if not patient:
                    continue

                patient_mrn_match = bool(
                    patient.mrn and patient.mrn.casefold() == identifier.casefold()
                )

                password_matches = False
                if patient.password:
                    password_matches = patient.check_password(password)
                else:
                    password_matches = (
                        password == '' or
                        password.casefold() == (patient.mrn or '').casefold() or
                        password.casefold() == (patient.hospital_number or '').casefold() or
                        password.casefold() == (patient.login_id or '').casefold()
                    )

                if password_matches:
                    connection.set_schema('public')
                    queue_login_notification(
                        recipient_email=patient.email,
                        user_name=patient.get_full_name(),
                        tenant_id=tenant.public_id,
                        ip_address=self.get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
                    refresh = RefreshToken()
                    refresh['patient_id'] = patient.id
                    refresh['tenant_id'] = str(tenant.public_id)
                    refresh['login_id'] = patient.login_id
                    refresh['is_patient'] = True

                    logger.info(f"[AUTH] Patient authenticated: patient_id={patient.id}, tenant={tenant.name}")
                    return Response({
                        'message': 'Patient login successful',
                        'patient': {
                            'id': patient.id,
                            'login_id': patient.login_id,
                            'hospital_number': patient.hospital_number,
                            'mrn': patient.mrn,
                            'full_name': patient.get_full_name(),
                            'tenant': tenant.name,
                        },
                        'tokens': {
                            'access_token': str(refresh.access_token),
                            'refresh_token': str(refresh),
                        },
                        'is_patient': True,
                    })

                if patient_mrn_match:
                    logger.info(
                        '[AUTH] Patient MRN found but password was invalid: patient_id=%s',
                        patient.id,
                    )
                    return Response(
                        {
                            'error': (
                                'Invalid patient password. This patient already has a password configured; '
                                'MRN may be used as the password only before password setup.'
                            )
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            finally:
                connection.set_schema('public')

        return None

    def _resolve_tenant_from_identifier(self, user_id):
        """Try to infer tenant from employee_id prefix (format: TENANT-ROLE-XXXX)."""
        if not user_id or '-' not in str(user_id):
            return None

        parts = str(user_id).split('-', 1)
        if len(parts) != 2:
            return None

        tenant_prefix = parts[0].upper()
        if len(tenant_prefix) < 2:
            return None

        return Tenant.objects.filter(code__istartswith=tenant_prefix).first()

    def _build_tenant_login_response(self, tenant, user, matched_by, request=None):
        if _tenant_requires_2fa(tenant):
            try:
                challenge_id = _start_tenant_email_2fa(tenant, user)
            except Exception:
                logger.exception('Unable to send tenant 2FA code to %s', user.email)
                return Response({'error': 'Unable to send the verification code.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({
                'requires_2fa': True,
                'tenant_2fa': True,
                'challenge_id': challenge_id,
                'tenant_id': str(tenant.public_id),
                'tenant_user_id': user.id,
                'message': 'A verification code was sent to your registered email address.',
            })

        queue_login_notification(
            recipient_email=user.email,
            user_name=user.get_full_name(),
            tenant_id=tenant.public_id,
            ip_address=self.get_client_ip(request) if request else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else None,
        )
        refresh = RefreshToken()
        refresh['user_id'] = user.id
        refresh['tenant_id'] = str(tenant.public_id)
        refresh['tenant_public_id'] = str(tenant.public_id)
        refresh['tenant_domain'] = tenant.domain
        refresh['is_tenant_user'] = True
        refresh['is_superadmin'] = bool(getattr(user, 'is_root_admin', False) or getattr(user, 'role', '') in ('super_admin', 'system_admin'))

        return Response({
            'message': 'Tenant admin login successful',
            'tenant': {
                'public_id': str(tenant.public_id),
                'name': tenant.name,
                'domain': tenant.domain,
            },
            'user': {
                'id': user.id,
                'user_id': user.employee_id or user.username,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'is_root_admin': user.is_root_admin,
                'is_active': user.is_active,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name(),
                'license_number': user.license_number,
                'mdcn_number': user.mdcn_number,
            },
            'tokens': {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            },
            'login_context': {
                'tenant_resolved_from': matched_by,
                'tenant_scoped_identifier_used': user.employee_id or user.username,
            },
            'is_tenant_user': True,
        })

    def finalize_response(self, request, response, *args, **kwargs):
        """Set HttpOnly auth cookies on successful login responses."""
        if isinstance(response, Response) and response.status_code == 200:
            data = response.data if hasattr(response, 'data') else None
            if isinstance(data, dict):
                tokens = data.get('tokens') or {}
                access_token = tokens.get('access_token') or data.get('access_token')
                refresh_token = tokens.get('refresh_token') or data.get('refresh_token')
                if access_token or refresh_token:
                    _set_auth_cookies(response, access_token, refresh_token)
        return super().finalize_response(request, response, *args, **kwargs)


    def authenticate_global_user(self, data, request):
        """Authenticate global user (super admin, support staff, etc)."""
        serializer = LoginSerializer(data=data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            if user.two_fa_enabled:
                logger.info(f"[2FA] 2FA required for user={user.username} id={user.id}")
                refresh = RefreshToken.for_user(user)
                refresh['two_fa_required'] = True
                refresh['two_fa_verified'] = False
                
                return Response({
                    'requires_2fa': True,
                    'user_id': user.id,
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                    'two_fa_methods': self.get_available_2fa_methods(user)
                })
            
            # No 2FA required, complete login
            return self.complete_login(user, request)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_available_2fa_methods(self, user):
        """Get available 2FA methods for user."""
        try:
            two_fa_settings = User2FA.objects.get(user=user)
            return two_fa_settings.get_available_methods()
        except User2FA.DoesNotExist:
            return ['totp']  # Default to TOTP if no settings exist
    
    def complete_login(self, user, request):
        """Complete login process without 2FA."""
        # Create user session (optional)
        try:
            session = UserSession.objects.create(
                user=user,
                session_key=request.session.session_key,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                expires_at=timezone.now() + timezone.timedelta(hours=1)
            )
        except:
            session = None
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        if session:
            refresh['session_id'] = session.session_key
        refresh['two_fa_verified'] = True
        refresh['is_global_user'] = True
        refresh['token_version'] = user.token_version
        refresh['is_superadmin'] = bool(user.is_superuser or user.role in ('super_admin', 'system_admin'))
        
        # Log security event
        SecurityEvent.objects.create(
            user=user,
            event_type=SecurityEvent.EventType.LOGIN_SUCCESS,
            severity=SecurityEvent.Severity.INFO,
            description='Login successful',
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        queue_login_notification(
            recipient_email=user.email,
            user_name=user.get_full_name(),
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            is_global_user=True,
        )
        
        return Response({
            'user': GlobalUserSerializer(user).data,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'requires_2fa': False,
            'is_global_user': True
        })
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PasswordResetRequestView(APIView):
    """Request a password reset token."""
    permission_classes = [permissions.AllowAny]
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        identifier = serializer.validated_data['identifier'].strip()
        ip_address = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        user = None
        user_type = None
        
        if identifier:
            user = GlobalUser.objects.filter(
                models_Q(username=identifier) |
                models_Q(email=identifier) |
                models_Q(employee_id=identifier)
            ).first()
            if user:
                user_type = 'global'
            else:
                from tenants.models import TenantUser
                user = TenantUser.objects.filter(
                    models_Q(username=identifier) |
                    models_Q(email=identifier) |
                    models_Q(employee_id=identifier)
                ).first()
                if user:
                    user_type = 'tenant'
        
        if user and user.email:
            recipient_email = user.email
            reset_token = PasswordResetToken.objects.create(
                email=recipient_email,
                token=f'{secrets.randbelow(10**12):012d}',
                expires_at=timezone.now() + timezone.timedelta(hours=1),
                user_type=user_type,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent
            )

            from .tasks import send_password_reset_email_task
            logger.info('Sending password reset email synchronously to %s', recipient_email)
            try:
                from smartcare_hms.email_delivery import dispatch_email_task
                dispatch_email_task(
                    send_password_reset_email_task,
                    kwargs={
                        'recipient_email': recipient_email,
                        'reset_token': reset_token.token,
                        'user_name': getattr(user, 'get_full_name', lambda: None)(),
                    },
                )
                logger.info('Password reset email dispatched to %s', recipient_email)
            except Exception:
                logger.exception('Unable to send password reset email to %s', recipient_email)
        
        return Response({
            'detail': 'If an account exists for this identifier, a password reset email has been sent.',
        })


class PasswordResetVerifyView(APIView):
    """Verify a reset token before allowing a password to be chosen."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reset_token = serializer.validated_data['reset_token']
        reset_token.verified_at = timezone.now()
        reset_token.save(update_fields=['verified_at'])
        return Response({'detail': 'Reset token verified. You can now choose a new password.'})


class PasswordResetConfirmView(APIView):
    """Confirm password reset with token."""
    permission_classes = [permissions.AllowAny]
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']
        
        user = None
        if reset_token.user_type == 'global':
            user = GlobalUser.objects.filter(id=reset_token.user_id).first()
        else:
            from tenants.models import TenantUser
            user = TenantUser.objects.filter(id=reset_token.user_id).first()
        
        if not user:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        if hasattr(user, 'set_password'):
            user.set_password(new_password)
        else:
            from django.contrib.auth.hashers import make_password
            user.password = make_password(new_password)
        user.password_changed_at = timezone.now()
        # Bump token_version to invalidate any previously issued JWTs.
        user.token_version += 1
        user.save()
        
        reset_token.is_used = True
        reset_token.save(update_fields=['is_used'])
        
        if hasattr(user, 'security_events'):
            SecurityEvent.objects.create(
                user=user,
                event_type='password_reset',
                severity='INFO',
                description='Password reset via token',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        
        return Response({'detail': 'Password reset successfully. You can now log in with your new password.'})


class TwoFAView(APIView):
    """Handle 2FA verification."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        if request.data.get('tenant_2fa'):
            return self.verify_tenant_email_code(request)

        logger.info(f"[2FA] Verification attempt for user_id={request.data.get('user_id')} code={request.data.get('code')}")
        serializer = TwoFASerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            two_fa_settings = serializer.validated_data['two_fa_settings']
            logger.info(f"[2FA] SUCCESS for user={user.username} method={serializer.validated_data['method']}")
            
            # Update 2FA settings
            two_fa_settings.last_used = timezone.now()
            two_fa_settings.failed_attempts = 0
            two_fa_settings.save()
            
            # Create user session
            session = UserSession.objects.create(
                user=user,
                session_key=request.session.session_key,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                expires_at=timezone.now() + timezone.timedelta(hours=1),
                device_info=self.get_device_info(request)
            )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            refresh['session_id'] = session.session_key
            refresh['two_fa_verified'] = True
            refresh['token_version'] = getattr(user, 'token_version', 1)
            
            # Log security event
            SecurityEvent.objects.create(
                user=user,
                event_type=SecurityEvent.EventType.TWO_FA_SUCCESS,
                severity=SecurityEvent.Severity.INFO,
                description='2FA verification successful',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                metadata={'method': serializer.validated_data['method']}
            )

            queue_login_notification(
                recipient_email=user.email,
                user_name=user.get_full_name(),
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                is_global_user=True,
            )
            
            return Response({
                'user': GlobalUserSerializer(user).data,
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'session_id': session.session_key
            })
        
        # Record failed 2FA attempt
        user_id = request.data.get('user_id')
        try:
            user = GlobalUser.objects.get(id=user_id)
            two_fa_settings = User2FA.objects.get(user=user)
            two_fa_settings.failed_attempts += 1
            two_fa_settings.last_failed_attempt = timezone.now()
            two_fa_settings.save()
            
            # Log security event
            SecurityEvent.objects.create(
                user=user,
                event_type=SecurityEvent.EventType.TWO_FA_FAILED,
                severity=SecurityEvent.Severity.MEDIUM,
                description='2FA verification failed',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
        except (GlobalUser.DoesNotExist, User2FA.DoesNotExist):
            pass
        
        logger.info(f"[2FA] FAILED for user_id={request.data.get('user_id')} errors={serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def verify_tenant_email_code(self, request):
        from django.db import connection

        challenge_id = request.data.get('challenge_id')
        code = str(request.data.get('code') or '').strip()
        challenge = cache.get(f'tenant-2fa:{challenge_id}') if challenge_id else None
        if not challenge or not secrets.compare_digest(str(challenge.get('code')), code):
            return Response({'error': 'Invalid or expired verification code.'}, status=status.HTTP_400_BAD_REQUEST)

        tenant = Tenant.objects.filter(public_id=challenge['tenant_id'], is_active=True).first()
        if not tenant:
            return Response({'error': 'Tenant not found.'}, status=status.HTTP_404_NOT_FOUND)

        connection.set_schema(tenant.schema_name)
        try:
            user = TenantUser.objects.filter(id=challenge['user_id'], is_active=True).first()
            if not user:
                return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
            refresh = RefreshToken()
            refresh['user_id'] = user.id
            refresh['tenant_id'] = str(tenant.public_id)
            refresh['tenant_public_id'] = str(tenant.public_id)
            refresh['tenant_domain'] = tenant.domain
            refresh['is_tenant_user'] = True
            refresh['two_fa_verified'] = True
            refresh['token_version'] = user.token_version
            cache.delete(f'tenant-2fa:{challenge_id}')
            return Response({
                'user': {
                    'id': user.id,
                    'user_id': user.employee_id or user.username,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'is_root_admin': user.is_root_admin,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name(),
                },
                'tenant': {'public_id': str(tenant.public_id), 'name': tenant.name, 'domain': tenant.domain},
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'is_tenant_user': True,
            })
        finally:
            connection.set_schema('public')
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_device_info(self, request):
        """Extract device information from request."""
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        if 'Mobile' in user_agent:
            device_type = 'mobile'
        elif 'Tablet' in user_agent:
            device_type = 'tablet'
        else:
            device_type = 'desktop'
        
        return {
            'device_type': device_type,
            'user_agent': user_agent[:500]
        }


class RSAKeyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing RSA keys."""
    serializer_class = RSASerializer
    
    def get_queryset(self):
        if not isinstance(self.request.user, GlobalUser):
            return RSAKey.objects.none()
        return RSAKey.objects.filter(user=self.request.user, is_active=True)
    
    def perform_create(self, serializer):
        # Generate RSA key pair
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        
        key_size = self.request.data.get('key_size', 2048)
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        
        # Get public key
        public_key = private_key.public_key()
        
        # Serialize keys
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Save key
        key = serializer.save(
            user=self.request.user,
            public_key=public_pem.decode(),
            private_key_encrypted=private_pem.decode(),
            expires_at=timezone.now() + timezone.timedelta(days=365)
        )
        
        # Log security event
        if isinstance(self.request.user, GlobalUser):
            SecurityEvent.objects.create(
                user=self.request.user,
                event_type=SecurityEvent.EventType.RSA_KEY_GENERATED,
                severity=SecurityEvent.Severity.INFO,
                description=f'RSA key {key.key_name} generated',
                ip_address=self.get_client_ip(self.request),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')
            )
    
    def perform_destroy(self, instance):
        if isinstance(self.request.user, GlobalUser):
            SecurityEvent.objects.create(
                user=self.request.user,
                event_type=SecurityEvent.EventType.RSA_KEY_REVOKED,
                severity=SecurityEvent.Severity.INFO,
                description=f'RSA key {instance.key_name} revoked',
                ip_address=self.get_client_ip(self.request),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')
            )
        
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def set_primary(self, request, pk=None):
        """Set RSA key as primary."""
        key = self.get_object()
        
        # Remove primary status from other keys
        RSAKey.objects.filter(user=request.user, is_primary=True).update(is_primary=False)
        
        # Set this key as primary
        key.is_primary = True
        key.save()
        
        return Response({'detail': 'Key set as primary'})
    
    @action(detail=True, methods=['post'])
    def rotate(self, request, pk=None):
        """Rotate RSA key."""
        key = self.get_object()
        key.rotate_key()
        
        return Response({'detail': 'Key rotated successfully'})
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class UserSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing user sessions."""
    serializer_class = UserSessionSerializer
    
    def get_queryset(self):
        if not isinstance(self.request.user, GlobalUser):
            return UserSession.objects.none()
        return UserSession.objects.filter(user=self.request.user, is_active=True)
    
    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Terminate a session."""
        session = self.get_object()
        session.terminate()
        
        return Response({'detail': 'Session terminated'})
    
    @action(detail=False, methods=['post'])
    def terminate_all(self, request):
        """Terminate all sessions except current one."""
        if not isinstance(request.user, GlobalUser):
            return Response(
                {'detail': 'Session management is only available for platform users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        UserSession.objects.filter(
            user=request.user,
            is_active=True
        ).exclude(
            session_key=request.session.session_key
        ).update(is_active=False)
        
        return Response({'detail': 'All other sessions terminated'})


class SecurityEventViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing security events."""
    serializer_class = SecurityEventSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if not isinstance(user, GlobalUser):
            return SecurityEvent.objects.none()
        
        # System admins can see all security events
        if user.is_superuser or user.role == 'super_admin':
            return SecurityEvent.objects.all()
        
        # System admins can see all security events
        if user.role == 'system_admin':
            return SecurityEvent.objects.all()
        
        # Support staff can see security events
        if user.role == 'support':
            return SecurityEvent.objects.all()
        
        # Regular users can only see their own security events
        return SecurityEvent.objects.filter(user=user)


class UserNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing user notifications."""
    serializer_class = UserNotificationSerializer
    
    def get_queryset(self):
        if not isinstance(self.request.user, GlobalUser):
            return UserNotification.objects.none()
        return UserNotification.objects.filter(
            user=self.request.user,
            is_read=False
        ).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        
        return Response({'detail': 'Notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read."""
        UserNotification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        
        return Response({'detail': 'All notifications marked as read'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = UserNotification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        return Response({'count': count})


class TwoFASetupView(APIView):
    """Setup 2FA for user."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get TOTP setup information."""
        if not isinstance(request.user, GlobalUser):
            return Response(
                {'error': '2FA setup is only available for platform users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = TOTPSetupSerializer(
            context={'user': request.user}
        )
        data = serializer.create({})
        
        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data['provisioning_uri'])
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        data['qr_code_image'] = f"data:image/png;base64,{img_str}"
        return Response(data)
    
    def post(self, request):
        """Verify TOTP setup."""
        if not isinstance(request.user, GlobalUser):
            return Response(
                {'error': '2FA setup is only available for platform users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        code = request.data.get('code')
        
        if not code:
            return Response(
                {'error': 'Code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get user's 2FA settings
        two_fa_settings, created = User2FA.objects.get_or_create(
            user=request.user
        )
        
        if not two_fa_settings.totp_secret:
            return Response(
                {'error': 'TOTP not set up'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify TOTP code
        totp = pyotp.TOTP(two_fa_settings.totp_secret)
        if totp.verify(code):
            two_fa_settings.totp_verified = True
            two_fa_settings.method = User2FA.TwoFAMethod.TOTP
            two_fa_settings.save()
            
            SecurityEvent.objects.create(
                user=request.user,
                event_type=SecurityEvent.EventType.TWO_FA_ENABLED,
                severity=SecurityEvent.Severity.INFO,
                description='TOTP 2FA enabled',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'detail': 'TOTP verified successfully'})
        
        SecurityEvent.objects.create(
            user=request.user,
            event_type=SecurityEvent.EventType.TWO_FA_FAILED,
            severity=SecurityEvent.Severity.MEDIUM,
            description='TOTP verification failed during setup',
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(
            {'error': 'Invalid TOTP code'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request):
        """Disable 2FA."""
        if not isinstance(request.user, GlobalUser):
            return Response(
                {'error': '2FA management is only available for platform users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            two_fa_settings = User2FA.objects.get(user=request.user)
            
            # Verify password
            password = request.data.get('password')
            if not password or not request.user.check_password(password):
                return Response(
                    {'error': 'Invalid password'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            two_fa_settings.delete()
            
            # Update user
            request.user.two_fa_enabled = False
            request.user.save()
            
            SecurityEvent.objects.create(
                user=request.user,
                event_type=SecurityEvent.EventType.TWO_FA_DISABLED,
                severity=SecurityEvent.Severity.INFO,
                description='2FA disabled',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'detail': '2FA disabled successfully'})
            
        except User2FA.DoesNotExist:
            return Response(
                {'error': '2FA not enabled'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class BackupCodeView(APIView):
    """Generate backup codes for 2FA."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get existing backup codes."""
        try:
            two_fa_settings = User2FA.objects.get(user=request.user)
            
            if not two_fa_settings.backup_codes:
                return Response({
                    'detail': 'No backup codes generated',
                    'codes': []
                })
            
            return Response({
                'codes': two_fa_settings.backup_codes,
                'generated_at': two_fa_settings.backup_codes_generated_at
            })
            
        except User2FA.DoesNotExist:
            return Response(
                {'error': '2FA not set up'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def post(self, request):
        """Generate new backup codes."""
        count = request.data.get('count', 10)
        
        # Verify password
        password = request.data.get('password')
        if not password or not request.user.check_password(password):
            return Response(
                {'error': 'Invalid password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            two_fa_settings = User2FA.objects.get(user=request.user)
            codes = two_fa_settings.generate_backup_codes(count)
            
            return Response({
                'codes': codes,
                'generated_at': two_fa_settings.backup_codes_generated_at
            })
            
        except User2FA.DoesNotExist:
            return Response(
                {'error': '2FA not set up'},
                status=status.HTTP_400_BAD_REQUEST
            )


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken


class TenantAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Token refresh serializer that also looks up TenantUser when GlobalUser is not found."""

    def validate(self, attrs):
        refresh_token = attrs.get('refresh')

        if refresh_token is None:
            raise TokenError('Refresh token is required')

        try:
            refresh = RefreshToken(refresh_token)
        except TokenError as exc:
            raise InvalidToken(str(exc))

        user_id = refresh.get('user_id')
        is_tenant_user = refresh.get('is_tenant_user', False)

        user = None
        if is_tenant_user:
            try:
                user = TenantUser.objects.get(id=user_id)
            except TenantUser.DoesNotExist:
                pass

        if user is None:
            try:
                user = GlobalUser.objects.get(id=user_id)
            except GlobalUser.DoesNotExist:
                raise InvalidToken('User not found')

        if not user.is_active:
            raise InvalidToken('User account is disabled')

        access = refresh.access_token
        access['is_tenant_user'] = is_tenant_user
        access['user_type'] = 'tenant' if is_tenant_user else 'global'
        access['role'] = getattr(user, 'role', '')
        access['is_superadmin'] = bool(getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ('super_admin', 'system_admin'))
        if is_tenant_user:
            access['full_name'] = user.get_full_name()
            access['username'] = user.username
            access['tenant_public_id'] = refresh.get('tenant_public_id') or refresh.get('tenant_id')
            access['tenant_id'] = refresh.get('tenant_id') or refresh.get('tenant_public_id')
            access['tenant_domain'] = refresh.get('tenant_domain')

        return {
            'access': str(access),
            'refresh': str(refresh),
        }


@api_view(['post'])
@permission_classes([AllowAny])
def tenant_aware_token_refresh(request):
    data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data or {})
    if not data.get('refresh'):
        cookie_refresh = request.COOKIES.get('refresh_token')
        if cookie_refresh:
            data['refresh'] = cookie_refresh
    serializer = TenantAwareTokenRefreshSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    response = Response(serializer.validated_data)
    token_data = serializer.validated_data
    access_token = token_data.get('access') or token_data.get('access_token')
    refresh_token = token_data.get('refresh') or token_data.get('refresh_token')
    if access_token or refresh_token:
        _set_auth_cookies(response, access_token, refresh_token)
    return response


@api_view(['post'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    refresh_token = request.data.get('refresh')
    user = request.user

    if refresh_token:
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh.get('user_id')
            if user_id and isinstance(user, GlobalUser) and str(user_id) == str(getattr(user, 'id', '')):
                UserSession.objects.filter(user=user, is_active=True).update(is_active=False)
        except Exception:
            pass

    if isinstance(user, GlobalUser):
        SecurityEvent.objects.create(
            user=user,
            event_type=SecurityEvent.EventType.LOGOUT,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

    response = Response({'detail': 'Logout successful'}, status=status.HTTP_200_OK)
    _clear_auth_cookies(response)
    return response