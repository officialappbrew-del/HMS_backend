from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from django.db import connection
import jwt
import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

from .models import UserSession, SecurityEvent, RSAKey
from tenants.models import Tenant, TenantUser


class RSAAuthentication(authentication.BaseAuthentication):
    """RSA-based authentication for API requests."""
    
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return None
        
        try:
            # Extract token
            auth_type, token = auth_header.split(' ', 1)
            
            if auth_type.lower() != 'rsa':
                return None
            
            # Decode token
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            
            user_id = payload.get('user_id')
            signature = payload.get('signature')
            timestamp = payload.get('timestamp')
            
            if not all([user_id, signature, timestamp]):
                raise AuthenticationFailed('Invalid token format')
            
            # Check token expiration (5 minutes)
            if timezone.now().timestamp() - timestamp > 300:
                raise AuthenticationFailed('Token expired')
            
            # Get user
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id, is_active=True)
            except User.DoesNotExist:
                raise AuthenticationFailed('User not found')
            
            # Get user's RSA key
            rsa_key = RSAKey.objects.filter(
                user=user,
                is_primary=True,
                is_active=True
            ).first()
            
            if not rsa_key:
                raise AuthenticationFailed('No RSA key found for user')
            
            # Verify signature
            if not self.verify_signature(rsa_key.public_key, token, signature):
                raise AuthenticationFailed('Invalid signature')
            
            # Update key usage
            rsa_key.last_used = timezone.now()
            rsa_key.usage_count += 1
            rsa_key.save()
            
            # Log security event
            SecurityEvent.objects.create(
                user=user,
                event_type=SecurityEvent.EventType.LOGIN_SUCCESS,
                severity=SecurityEvent.Severity.INFO,
                description='RSA authentication successful',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return (user, None)
            
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')
        except Exception as e:
            raise AuthenticationFailed(str(e))
    
    def verify_signature(self, public_key_pem, data, signature):
        """Verify RSA signature."""
        try:
            # Load public key
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode(),
                backend=default_backend()
            )
            
            # Hash the data
            data_hash = hashlib.sha256(data.encode()).digest()
            
            # Verify signature
            public_key.verify(
                bytes.fromhex(signature),
                data_hash,
                padding=rsa.PSS(
                    mgf=rsa.MGF1(hashes.SHA256()),
                    salt_length=rsa.PSS.MAX_LENGTH
                ),
                algorithm=hashes.SHA256()
            )
            return True
            
        except InvalidSignature:
            return False
        except Exception:
            return False
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class JWTAuthentication(authentication.BaseAuthentication):
    """JWT-based authentication for both global users and tenant users."""

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return None

        try:
            auth_type, token = auth_header.split(' ', 1)

            if auth_type.lower() != 'bearer':
                return None

            payload = jwt.decode(
                token,
                settings.SIMPLE_JWT['SIGNING_KEY'],
                algorithms=['HS256']
            )

            user_id = payload.get('user_id')
            session_id = payload.get('session_id')

            if not user_id:
                raise AuthenticationFailed('Invalid token')

            # Tenant user token path
            if payload.get('is_tenant_user'):
                tenant_public_id = payload.get('tenant_public_id') or payload.get('tenant_id')
                tenant = None

                if tenant_public_id:
                    tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                    if tenant is None and str(tenant_public_id).isdigit():
                        tenant = Tenant.objects.filter(id=int(tenant_public_id)).first()

                if tenant is None and payload.get('tenant_domain'):
                    tenant = Tenant.objects.filter(domain=payload.get('tenant_domain')).first()

                if tenant is None:
                    raise AuthenticationFailed('Tenant not found')

                try:
                    connection.set_schema(tenant.schema_name)
                    user = None

                    # First prefer the database id if the token stores one.
                    if user_id is not None and str(user_id).isdigit():
                        user = TenantUser.objects.filter(
                            id=int(user_id),
                            is_active=True,
                        ).first()

                    # Fall back to the tenant-scoped login identifiers.
                    if user is None:
                        user = TenantUser.objects.filter(
                            employee_id=str(user_id),
                            is_active=True,
                        ).first()
                    if user is None:
                        user = TenantUser.objects.filter(
                            username=str(user_id),
                            is_active=True,
                        ).first()
                finally:
                    connection.set_schema_to_public()

                if not user:
                    raise AuthenticationFailed('User not found')

                user.is_authenticated = True
                user.is_tenant_user = True
                user.tenant = tenant
                user.tenant_user = user
                user.tenant_public_id = str(tenant.public_id)
                user.tenant_domain = tenant.domain
                user.is_staff = user.role in {
                    'admin', 'doctor', 'nurse', 'pharmacist', 'lab_tech',
                    'receptionist', 'accountant', 'hr_manager',
                    'inventory_manager'
                }
                return (user, payload)

            # Global user path
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id, is_active=True)
                user.is_tenant_user = payload.get('is_tenant_user', False)
                tenant_id = payload.get('tenant_id')
                if tenant_id:
                    user.tenant_id = tenant_id
            except User.DoesNotExist:
                raise AuthenticationFailed('User not found')

            if session_id:
                try:
                    session = UserSession.objects.get(
                        session_key=session_id,
                        user=user,
                        is_active=True
                    )

                    if session.is_expired():
                        session.terminate()
                        raise AuthenticationFailed('Session expired')

                    session.last_activity = timezone.now()
                    session.save()
                except UserSession.DoesNotExist:
                    raise AuthenticationFailed('Invalid session')

            # if getattr(user, 'two_fa_enabled', False) and not payload.get('two_fa_verified', False):
            #     raise AuthenticationFailed('2FA verification required')

            return (user, payload)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')
        except Exception as e:
            raise AuthenticationFailed(str(e))