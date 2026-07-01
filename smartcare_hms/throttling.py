"""
Rate limiting/throttling configuration for SmartCare HMS API.

Implements different throttle rates for different endpoints:
- Authentication endpoints: 5 attempts per minute
- Password reset: 3 attempts per hour
- API endpoints: 100 requests per hour per user
- Anonymous users: Limited to prevent abuse
"""

from decouple import config
from rest_framework.throttling import SimpleRateThrottle, AnonRateThrottle
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import Throttled
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
import logging
import time

logger = logging.getLogger(__name__)


class RateLimitMiddleware(MiddlewareMixin):
    """Global middleware that rate-limits requests by IP/user across the API."""

    WINDOW_SECONDS = config('RATE_LIMIT_WINDOW_SECONDS', default=60, cast=int)
    MAX_REQUESTS = config('RATE_LIMIT_MAX_REQUESTS', default=200, cast=int)
    EXEMPT_PATH_PREFIXES = tuple(
        prefix.strip() for prefix in config(
            'RATE_LIMIT_EXEMPT_PATH_PREFIXES',
            default='/admin/,/static/,/media/,/health/,/metrics/'
        ).split(',') if prefix.strip()
    )

    def process_request(self, request):
        if request.path.startswith(self.EXEMPT_PATH_PREFIXES):
            return None

        identifier = self.get_identifier(request)
        now = time.time()
        key = f'ratelimit:{request.method}:{identifier}:{request.path}'
        bucket = cache.get(key, [])
        if not isinstance(bucket, list):
            bucket = []

        bucket = [timestamp for timestamp in bucket if now - timestamp < self.WINDOW_SECONDS]
        if len(bucket) >= self.MAX_REQUESTS:
            logger.warning('Rate limit exceeded for %s on %s', identifier, request.path)
            return JsonResponse(
                {'detail': 'Too many requests. Please try again shortly.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        bucket.append(now)
        cache.set(key, bucket, self.WINDOW_SECONDS)
        return None

    def get_identifier(self, request):
        user = getattr(request, 'user', None)
        if getattr(user, 'is_authenticated', False):
            return f'user:{user.pk}'

        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


class AuthenticationThrottle(SimpleRateThrottle):
    """
    Throttle for authentication endpoints (login, password reset).
    
    Rate is configured via the AUTH_THROTTLE_RATE environment variable.
    """
    scope = 'auth'
    THROTTLE_RATES = {'auth': config('AUTH_THROTTLE_RATE', default='5/min')}

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Use submitted login identifier when available, otherwise fallback to IP."""
        username = self.get_login_identifier(request)
        if username:
            return f'auth_user:{username}'

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def get_login_identifier(self, request):
        if not hasattr(request, 'data'):
            return None
        username = request.data.get('username') or request.data.get('identifier') or request.data.get('user_id')
        if isinstance(username, str):
            return username.strip().lower()
        return None

    def throttle_failure(self, request, wait):
        message = 'Too many login attempts. Please try again later.'
        if wait:
            message = f'Too many login attempts. Try again in {int(wait)} seconds.'
        raise Throttled(detail=message, wait=wait)


class PasswordResetThrottle(SimpleRateThrottle):
    """
    Throttle for password reset requests.
    
    Rate is configured via PASSWORD_RESET_THROTTLE_RATE.
    """
    scope = 'password_reset'
    THROTTLE_RATES = {
        'password_reset': config('PASSWORD_RESET_THROTTLE_RATE', default='3/hour')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Get client IP address as identifier."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class PasswordResetConfirmThrottle(SimpleRateThrottle):
    """
    Throttle for password reset confirmation (changing password).
    
    Rate is configured via PASSWORD_RESET_CONFIRM_THROTTLE_RATE.
    """
    scope = 'password_reset_confirm'
    THROTTLE_RATES = {
        'password_reset_confirm': config('PASSWORD_RESET_CONFIRM_THROTTLE_RATE', default='5/hour')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Get client IP address as identifier."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class UserAPIThrottle(SimpleRateThrottle):
    """
    Throttle for general API endpoints.
    
    Rate: 100 requests per hour per user (authenticated)
           50 requests per hour per IP (anonymous)
    """
    scope = 'api'
    THROTTLE_RATES = {
        'api': config('API_THROTTLE_RATE', default='100/hour')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """
        Use user ID if authenticated, otherwise use IP address.
        """
        user = getattr(request, 'user', None)
        if getattr(user, 'is_authenticated', False):
            return f"user_{user.id}"
        
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return f"ip_{x_forwarded_for.split(',')[0].strip()}"
        return f"ip_{request.META.get('REMOTE_ADDR', '')}"


class AnonymousUserThrottle(AnonRateThrottle):
    """
    Throttle for anonymous users.
    
    Rate: 50 requests per hour per IP address
    """
    scope = 'anon'
    THROTTLE_RATES = {
        'anon': config('ANON_THROTTLE_RATE', default='50/hour')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginAttemptThrottle(SimpleRateThrottle):
    """
    Specific throttle for login attempts.
    
    Rate is configured via LOGIN_ATTEMPT_THROTTLE_RATE.
    """
    scope = 'login_attempt'
    THROTTLE_RATES = {
        'login_attempt': config('LOGIN_ATTEMPT_THROTTLE_RATE', default='5/15min')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Get client IP address as identifier."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class TwoFAThrottle(SimpleRateThrottle):
    """
    Throttle for 2FA verification attempts.
    
    Rate is configured via TWO_FA_THROTTLE_RATE.
    """
    scope = '2fa'
    THROTTLE_RATES = {
        '2fa': config('TWO_FA_THROTTLE_RATE', default='5/15min')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Get client IP address as identifier."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class AuditTrailThrottle(SimpleRateThrottle):
    """
    Throttle for audit trail and logging endpoints.
    
    Rate is configured via AUDIT_THROTTLE_RATE.
    """
    scope = 'audit'
    THROTTLE_RATES = {
        'audit': config('AUDIT_THROTTLE_RATE', default='1000/hour')
    }

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
    
    def get_ident(self, request):
        """Use user ID if authenticated."""
        user = getattr(request, 'user', None)
        if getattr(user, 'is_authenticated', False):
            return f"user_{user.id}"
        return request.META.get('REMOTE_ADDR', '')


# Configure REST Framework throttle settings
DEFAULT_THROTTLE_CLASSES = [
    'smartcare_hms.throttling.UserAPIThrottle',
    'smartcare_hms.throttling.AnonymousUserThrottle',
]

DEFAULT_THROTTLE_RATES = {
    'api': '100/hour',  # General API
    'anon': '50/hour',  # Anonymous users
    'auth': '5/min',  # Authentication
    'password_reset': '3/hour',  # Password reset requests
    'password_reset_confirm': '5/hour',  # Password reset confirmation
    'login_attempt': '5/15min',  # Login attempts
    '2fa': '5/15min',  # 2FA verification
    'audit': '1000/hour',  # Audit operations
}
