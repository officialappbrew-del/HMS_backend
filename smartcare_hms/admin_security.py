"""
Admin security middleware.

Restricts access to the Django admin site (/admin/) to an optional IP
allowlist configured via ``ADMIN_ALLOWED_IPS`` in settings. When the allowlist
is empty, admin access is allowed from any IP (development default). When it is
non-empty, requests to /admin/ from IPs outside the allowlist are rejected with
HTTP 403.

The client IP honours X-Forwarded-For, which is only trusted because the app is
required to sit behind a trusted reverse proxy (see SECURE_PROXY_SSL_HEADER /
PROXY_COUNT in settings).
"""
from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings


class AdminIPRestrictMiddleware(MiddlewareMixin):
    """Reject /admin/ requests from IPs not in the ADMIN_ALLOWED_IPS allowlist."""

    ALLOWED_IPS = getattr(settings, 'ADMIN_ALLOWED_IPS', [])

    def process_request(self, request):
        if not self.ALLOWED_IPS:
            # Allowlist disabled - allow admin from any IP (dev default).
            return None

        if not request.path.startswith('/admin/'):
            return None

        client_ip = self.get_client_ip(request)
        if client_ip not in self.ALLOWED_IPS:
            return HttpResponseForbidden('Administrative access denied.')

        return None

    def get_client_ip(self, request):
        """Return the client IP, honouring X-Forwarded-For behind a trusted proxy."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if x_forwarded_for:
            num_proxies = getattr(settings, 'SECURE_PROXY_SSL_HEADER_NUM_PROXIES', 1)
            parts = [p.strip() for p in x_forwarded_for.split(',') if p.strip()]
            # The rightmost entry is the original client when behind N trusted
            # proxies; take the appropriate one.
            if parts and num_proxies >= 1:
                return parts[-num_proxies]
        return request.META.get('REMOTE_ADDR', '')
