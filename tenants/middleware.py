"""
Custom tenant middleware that supports header-based tenant resolution.
This allows testing without configuring DNS entries.
"""
from django_tenants.middleware.main import TenantMainMiddleware
from django.db import connection
from django.conf import settings
from tenants.models import Tenant
import threading
import jwt

# Thread-local storage for current tenant
_thread_locals = threading.local()


def get_current_tenant():
    """Get the current tenant from thread-local storage."""
    return getattr(_thread_locals, 'tenant', None)


def set_current_tenant(tenant):
    """Set the current tenant in thread-local storage."""
    _thread_locals.tenant = tenant


class HeaderTenantMiddleware(TenantMainMiddleware):
    """
    Extended TenantMainMiddleware that supports header-based tenant resolution.
    This allows testing without configuring DNS entries.
    """
    
    PUBLIC_SCHEMA_URLS = [
        '/api/v1/auth/',
        '/api/v1/core/',
        '/api/v1/tenants/active-tenants/',
        '/api/v1/tenants/invitations/accept/',
        '/admin/',
        '/api/docs/',
        '/swagger/',
        '/redoc/',
        '/test-public/',
    ]
    
    def process_request(self, request):
        """Override to support header-based tenant resolution."""
        # Check if this is a public schema URL
        path = request.path_info
        is_public = any(path.startswith(url) for url in self.PUBLIC_SCHEMA_URLS)
        
        if is_public:
            # For public URLs, use the public schema
            connection.set_schema_to_public()
            return
        
        # Try to get tenant from header first
        tenant_id = request.headers.get('X-Tenant-ID')
        if tenant_id:
            try:
                tenant = Tenant.objects.filter(public_id=tenant_id).first()
                if tenant is None and tenant_id.isdigit():
                    tenant = Tenant.objects.filter(id=int(tenant_id)).first()
                if tenant:
                    set_current_tenant(tenant)
                    connection.set_tenant(tenant)
                    return
            except (Tenant.DoesNotExist, ValueError, TypeError):
                pass

        # Try JWT claims directly from the Authorization header before auth runs.
        auth_header = request.headers.get('Authorization', '')
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
                is_tenant_user = payload.get('is_tenant_user')
                if is_tenant_user and tenant_public_id:
                    tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                    if tenant is None and str(tenant_public_id).isdigit():
                        tenant = Tenant.objects.filter(id=int(tenant_public_id)).first()
                    if tenant:
                        set_current_tenant(tenant)
                        connection.set_tenant(tenant)
                        return
            except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
                pass
        
        # Try to get TEST tenant for development
        try:
            tenant = Tenant.objects.get(code='TEST')
            set_current_tenant(tenant)
            connection.set_tenant(tenant)
            return
        except Tenant.DoesNotExist:
            pass
        
        # If user is authenticated but no tenant found from header, get from JWT token
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            # Try to get tenant_public_id from JWT token claims first
            tenant_public_id = getattr(request.user, 'tenant_public_id', None)
            if tenant_public_id:
                try:
                    tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                    if tenant:
                        set_current_tenant(tenant)
                        connection.set_tenant(tenant)
                        return
                except (Tenant.DoesNotExist, ValueError, TypeError):
                    pass

            # Backward-compatible lookup from JWT tenant_id claims
            tenant_id = getattr(request.user, 'tenant_id', None)
            if tenant_id:
                try:
                    tenant = Tenant.objects.filter(public_id=tenant_id).first()
                    if tenant is None and str(tenant_id).isdigit():
                        tenant = Tenant.objects.filter(id=int(tenant_id)).first()
                    if tenant:
                        set_current_tenant(tenant)
                        connection.set_tenant(tenant)
                        return
                except (Tenant.DoesNotExist, ValueError, TypeError):
                    pass
            
            # Try to get tenant from tenant_user relationship
            if hasattr(request.user, 'tenant_user') and request.user.tenant_user:
                tenant = request.user.tenant_user.tenant
                set_current_tenant(tenant)
                connection.set_tenant(tenant)
                return
            
            # For authenticated users without tenant, use public schema
            connection.set_schema_to_public()
            return
        
        # Fall back to parent implementation for domain-based resolution
        super().process_request(request)
