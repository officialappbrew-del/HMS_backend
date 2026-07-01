"""
Logging middleware for request/response tracking and correlation IDs.

This middleware captures request details, generates correlation IDs,
and enriches logs with context information.
"""

import logging
import uuid
import time
import json
import threading
import jwt
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser
from django.conf import settings


logger = logging.getLogger('request_response')

# Thread-local storage for request context
_request_context = threading.local()


class ContextVar:
    """Simple context variable holder for threading."""
    def __init__(self, name, default):
        self.name = name
        self.default = default
    
    def set(self, value):
        if not hasattr(_request_context, self.name):
            setattr(_request_context, self.name, {})
        getattr(_request_context, self.name)['value'] = value
    
    def get(self):
        if not hasattr(_request_context, self.name):
            return self.default
        return getattr(_request_context, self.name).get('value', self.default)


# Context variables
correlation_id_var = ContextVar('correlation_id', 'N/A')
user_id_var = ContextVar('user_id', 'N/A')
tenant_id_var = ContextVar('tenant_id', 'N/A')
method_var = ContextVar('method', 'N/A')
path_var = ContextVar('path', 'N/A')
ip_address_var = ContextVar('ip_address', 'N/A')


def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'N/A')
    return ip


def extract_jwt_user_id(request):
    """
    Extract user_id and tenant_id from JWT token in Authorization header.
    
    Returns:
        Tuple of (user_id, tenant_id) or (None, None) if no valid token
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    
    if not auth_header:
        return None, None
    
    try:
        # Extract token from "Bearer <token>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None, None
        
        token = parts[1]
        
        # Decode JWT without verification (just to extract claims for logging)
        # This is safe for logging purposes - we're not using it for authentication
        payload = jwt.decode(
            token,
            settings.SIMPLE_JWT['SIGNING_KEY'],
            algorithms=['HS256']
        )
        
        user_id = payload.get('user_id')
        tenant_id = payload.get('tenant_id') or payload.get('tenant_public_id')
        
        return user_id, tenant_id
    except (jwt.InvalidTokenError, jwt.DecodeError, AttributeError, KeyError):
        # Token is invalid or settings not configured - ignore silently
        return None, None
    except Exception:
        # Any other error - ignore silently
        return None, None


class CorrelationIdMiddleware(MiddlewareMixin):
    """
    Middleware to add correlation IDs to requests and logs.
    
    Each request gets a unique ID that can be used to trace
    the request through the entire system.
    """

    CORRELATION_ID_HEADER = 'X-Correlation-ID'

    def process_request(self, request):
        """Generate correlation ID for the request."""
        # Check if correlation ID was provided in request headers
        correlation_id = request.META.get(f'HTTP_{self.CORRELATION_ID_HEADER.upper().replace("-", "_")}')

        # Generate a new one if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        request.correlation_id = correlation_id
        correlation_id_var.set(correlation_id)
        return None

    def process_response(self, request, response):
        """Add correlation ID to response headers."""
        response['X-Correlation-ID'] = getattr(request, 'correlation_id', str(uuid.uuid4()))
        return response


class RequestResponseLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all requests and responses.
    
    Captures:
    - Request method, path, query parameters
    - Response status code and time taken
    - User information (from JWT token or session)
    - Tenant information
    - Request/response sizes
    """

    EXCLUDED_PATHS = [
        '/health/',
        '/metrics/',
        '/static/',
        '/media/',
    ]

    def should_log(self, path):
        """Check if path should be logged."""
        return not any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS)

    def process_request(self, request):
        """Log incoming request."""
        request._start_time = time.time()

        if not self.should_log(request.path):
            return None

        # Extract request details
        method = request.method
        path = request.path
        ip_address = get_client_ip(request)
        
        # Try to get user_id from JWT token first
        jwt_user_id, jwt_tenant_id = extract_jwt_user_id(request)
        
        # Fall back to request.user if JWT parsing failed
        if jwt_user_id is None:
            user = request.user if hasattr(request, 'user') else AnonymousUser()
            user_id = user.id if user.is_authenticated else 'Anonymous'
            tenant_id = 'N/A'
        else:
            user_id = jwt_user_id
            tenant_id = jwt_tenant_id or 'N/A'

        # Get tenant info if using multi-tenancy and not from JWT
        if tenant_id == 'N/A':
            tenant_obj = getattr(request, 'tenant', {})
            if hasattr(tenant_obj, 'id'):
                tenant_id = tenant_obj.id
            else:
                tenant_id = request.META.get('HTTP_X_TENANT_ID', 'N/A')

        # Store in context variables
        method_var.set(method)
        path_var.set(path)
        user_id_var.set(user_id)
        tenant_id_var.set(tenant_id)
        ip_address_var.set(ip_address)

        # Build request log
        request_log = {
            'event': 'request_started',
            'method': method,
            'path': path,
            'query_string': request.META.get('QUERY_STRING', ''),
            'user_id': user_id,
            'tenant_id': tenant_id,
            'ip_address': ip_address,
            'user_agent': request.META.get('HTTP_USER_AGENT', 'N/A'),
        }

        # Store context in request for access in response logging
        request._log_context = {
            'user_id': user_id,
            'tenant_id': tenant_id,
            'ip_address': ip_address,
            'method': method,
            'path': path,
        }

        logger.info(json.dumps(request_log))

        return None

    def process_response(self, request, response):
        """Log response."""
        if not self.should_log(request.path):
            return response

        # Calculate request duration
        duration = (time.time() - request._start_time) * 1000  # Convert to ms
        status_code = response.status_code

        # Get stored context
        context = getattr(request, '_log_context', {})

        # Build response log
        response_log = {
            'event': 'request_completed',
            'method': context.get('method', 'N/A'),
            'path': context.get('path', 'N/A'),
            'status_code': status_code,
            'duration_ms': round(duration, 2),
            'user_id': context.get('user_id', 'N/A'),
            'tenant_id': context.get('tenant_id', 'N/A'),
            'ip_address': context.get('ip_address', 'N/A'),
        }

        # Log slow requests
        if duration > 1000:  # More than 1 second
            response_log['slow_request'] = True

        # Determine log level based on status code
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        logger.log(log_level, json.dumps(response_log))

        return response

    def process_exception(self, request, exception):
        """Log exceptions during request processing."""
        if not self.should_log(request.path):
            return None

        context = getattr(request, '_log_context', {})
        duration = (time.time() - request._start_time) * 1000

        exception_log = {
            'event': 'request_exception',
            'method': context.get('method', 'N/A'),
            'path': context.get('path', 'N/A'),
            'user_id': context.get('user_id', 'N/A'),
            'tenant_id': context.get('tenant_id', 'N/A'),
            'ip_address': context.get('ip_address', 'N/A'),
            'exception': str(exception),
            'exception_type': exception.__class__.__name__,
            'duration_ms': round(duration, 2),
        }

        logger.error(json.dumps(exception_log), exc_info=True)

        return None


class EnrichLoggingContextMiddleware(MiddlewareMixin):
    """
    Middleware to enrich logging context with request information.
    
    This updates context variables that the ContextFilter will use
    to enrich all log records made during request processing.
    """

    def process_request(self, request):
        """Add correlation ID and context to logging."""
        correlation_id = getattr(request, 'correlation_id', str(uuid.uuid4()))
        
        # Try to get user_id from JWT token first
        jwt_user_id, jwt_tenant_id = extract_jwt_user_id(request)
        
        if jwt_user_id is None:
            user = request.user if hasattr(request, 'user') else AnonymousUser()
            user_id = user.id if user.is_authenticated else 'Anonymous'
            tenant_id = 'N/A'
        else:
            user_id = jwt_user_id
            tenant_id = jwt_tenant_id or 'N/A'

        # Store in request for middleware access
        request.correlation_id = correlation_id
        request.user_id = user_id
        request.tenant_id = tenant_id

        # Update context variables
        correlation_id_var.set(correlation_id)
        user_id_var.set(user_id)
        tenant_id_var.set(tenant_id)

        return None


