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


class HeaderTenantMiddleware(TenantMainMiddleware):
    """
    Extended TenantMainMiddleware that supports header-based tenant resolution.
    This allows testing without configuring DNS entries.
    """

    PUBLIC_SCHEMA_URLS = [
        '/api/v1/auth/',
        '/api/v1/core/',
        '/api/v1/core/health/',
        '/api/v1/superadmin/',
        '/api/v1/hr/',
        '/api/v1/accounts/',
        '/api/v1/tenants/active-tenants/',
        '/api/v1/tenants/invitations/accept/',
        '/api/v1/tenants/invitations/accept',
        '/api/v1/tenants/self-signup/',
        '/api/v1/tenants/verify-email/',
        '/api/v1/tenants/public-config/',
        '/admin/',
        '/api/docs/',
        '/swagger/',
        '/redoc/',
        '/test-public/',
        '/health/',
        '/media/',
        '/static/',
    ]

    def _resolve_tenant_from_header(self, request):
        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            return None
        try:
            tenant = Tenant.objects.filter(public_id=tenant_id).first()
            if tenant is None and tenant_id.isdigit():
                tenant = Tenant.objects.filter(id=int(tenant_id)).first()
            return tenant
        except (ValueError, TypeError):
            return None

    def _resolve_tenant_from_jwt(self, request):
        # Reuse the JWT payload already decoded (and cached) by the logging
        # middleware to avoid redundant HMAC verification on the hot path.
        from smartcare_hms.logging_middleware import get_jwt_payload
        try:
            payload = get_jwt_payload(request)
            if not payload:
                return None
            tenant_public_id = payload.get('tenant_public_id') or payload.get('tenant_id')
            is_tenant_user = payload.get('is_tenant_user')
            if is_tenant_user and tenant_public_id:
                tenant = Tenant.objects.filter(public_id=tenant_public_id).first()
                if tenant is None and str(tenant_public_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(tenant_public_id)).first()
                return tenant
        except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
            pass
        return None

    def _resolve_tenant_from_user(self, request):
        if request.user and request.user.is_authenticated:
            if hasattr(request.user, 'tenant_user') and request.user.tenant_user:
                return request.user.tenant_user.tenant
            if hasattr(request.user, 'tenant') and request.user.tenant:
                return request.user.tenant
        return None

    def process_request(self, request):
        """Override to support header-based tenant resolution."""
        path = request.path_info
        is_public = any(path.startswith(url) for url in self.PUBLIC_SCHEMA_URLS)

        # Priority: authenticated user > JWT token > X-Tenant-ID header > domain
        tenant = self._resolve_tenant_from_user(request)
        if tenant:
            request.tenant = tenant
            connection.set_tenant(tenant)
            return

        tenant = self._resolve_tenant_from_jwt(request)
        if tenant:
            request.tenant = tenant
            connection.set_tenant(tenant)
            return

        tenant = self._resolve_tenant_from_header(request)
        if tenant:
            request.tenant = tenant
            connection.set_tenant(tenant)
            return

        if is_public:
            connection.set_schema_to_public()
            request.tenant = None
            return

        # Fall back to parent implementation for domain-based resolution
        super().process_request(request)
