"""
Enterprise-grade logging configuration for SmartCare HMS.

This module provides a comprehensive logging setup including:
- Structured JSON logging
- Rotating file handlers
- Request correlation tracking
- Performance monitoring
- Error context capture
"""

import os
import json
import logging
import logging.handlers
from pathlib import Path
from pythonjsonlogger import jsonlogger
from datetime import datetime


class ContextFilter(logging.Filter):
    """
    Add contextual information to log records.
    Captures request ID, user info, tenant, etc.
    """

    def filter(self, record):
        """Add context to log record."""
        # Add timestamp in ISO format
        record.timestamp = datetime.utcnow().isoformat()

        # Add hostname
        import socket
        record.hostname = socket.gethostname()

        # Add environment
        record.environment = os.getenv('ENVIRONMENT', 'development')

        # Get context from context variables (set by middleware)
        try:
            from .logging_middleware import (
                correlation_id_var, user_id_var, tenant_id_var, method_var, path_var, ip_address_var
            )
            record.request_id = correlation_id_var.get()
            record.user_id = user_id_var.get()
            record.tenant_id = tenant_id_var.get()
            record.method = method_var.get()
            record.path = path_var.get()
            record.ip_address = ip_address_var.get()
        except (ImportError, AttributeError):
            # Fallback if context variables aren't available
            record.request_id = getattr(record, 'request_id', 'N/A')
            record.user_id = getattr(record, 'user_id', 'N/A')
            record.tenant_id = getattr(record, 'tenant_id', 'N/A')
            record.method = getattr(record, 'method', 'N/A')
            record.path = getattr(record, 'path', 'N/A')
            record.ip_address = getattr(record, 'ip_address', 'N/A')

        return True


class RotatingFileHandlerWithJSON(logging.handlers.RotatingFileHandler):
    """Rotating file handler with JSON formatting."""

    def __init__(self, filename, maxBytes=10485760, backupCount=10, *args, **kwargs):
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount, *args, **kwargs)


def setup_logging(base_dir, debug=False):
    """
    Configure all loggers for the application.

    Args:
        base_dir: Base directory for log files
        debug: Whether running in debug mode
    """
    log_dir = Path(base_dir) / 'logs'
    log_dir.mkdir(exist_ok=True)

    # Create formatters
    verbose_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # JSON formatter for structured logging
    json_formatter = jsonlogger.JsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s %(request_id)s %(user_id)s %(tenant_id)s %(method)s %(path)s %(ip_address)s %(hostname)s %(environment)s'
    )

    # Simple formatter for console output
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler (DEBUG/INFO in development, WARNING in production)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    console_handler.setFormatter(simple_formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    # General Application Log (All levels, JSON format, rotating)
    app_log_file = log_dir / 'app.log'
    app_handler = RotatingFileHandlerWithJSON(
        str(app_log_file),
        maxBytes=10485760,  # 10 MB
        backupCount=20,
        encoding='utf-8'
    )
    app_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    app_handler.setFormatter(json_formatter)
    app_handler.addFilter(ContextFilter())

    # Error Log (ERROR and CRITICAL only, rotating)
    error_log_file = log_dir / 'error.log'
    error_handler = RotatingFileHandlerWithJSON(
        str(error_log_file),
        maxBytes=10485760,  # 10 MB
        backupCount=20,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(ContextFilter())

    # Performance/Slow Query Log (rotating)
    performance_log_file = log_dir / 'performance.log'
    performance_handler = RotatingFileHandlerWithJSON(
        str(performance_log_file),
        maxBytes=5242880,  # 5 MB
        backupCount=10,
        encoding='utf-8'
    )
    performance_handler.setLevel(logging.WARNING)
    performance_handler.setFormatter(json_formatter)
    performance_handler.addFilter(ContextFilter())

    # Request/Response Log (rotating)
    request_log_file = log_dir / 'requests.log'
    request_handler = RotatingFileHandlerWithJSON(
        str(request_log_file),
        maxBytes=10485760,  # 10 MB
        backupCount=20,
        encoding='utf-8'
    )
    request_handler.setLevel(logging.INFO)
    request_handler.setFormatter(json_formatter)
    request_handler.addFilter(ContextFilter())

    # Audit Log (rotating)
    audit_log_file = log_dir / 'audit.log'
    audit_handler = RotatingFileHandlerWithJSON(
        str(audit_log_file),
        maxBytes=10485760,  # 10 MB
        backupCount=20,
        encoding='utf-8'
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(json_formatter)
    audit_handler.addFilter(ContextFilter())

    # Django logger
    django_logger = logging.getLogger('django')
    django_logger.setLevel(logging.INFO if debug else logging.WARNING)
    django_logger.addHandler(console_handler)
    django_logger.addHandler(app_handler)
    django_logger.addHandler(error_handler)
    django_logger.propagate = False

    # Django database logger (slow queries)
    django_db_logger = logging.getLogger('django.db.backends')
    django_db_logger.setLevel(logging.DEBUG if debug else logging.WARNING)
    django_db_logger.addHandler(performance_handler)
    django_db_logger.propagate = False

    # Django security logger
    django_security_logger = logging.getLogger('django.security')
    django_security_logger.setLevel(logging.INFO)
    django_security_logger.addHandler(console_handler)
    django_security_logger.addHandler(error_handler)
    django_security_logger.propagate = False

    # REST Framework logger
    rest_framework_logger = logging.getLogger('rest_framework')
    rest_framework_logger.setLevel(logging.INFO if debug else logging.WARNING)
    rest_framework_logger.addHandler(app_handler)
    rest_framework_logger.addHandler(error_handler)
    rest_framework_logger.propagate = False

    # Application logger (for your app code)
    app_logger = logging.getLogger('smartcare')
    app_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_handler)
    app_logger.addHandler(error_handler)
    app_logger.propagate = False

    # Request/Response logger
    request_response_logger = logging.getLogger('request_response')
    request_response_logger.setLevel(logging.INFO)
    request_response_logger.addHandler(request_handler)
    request_response_logger.propagate = False

    # Audit logger (for tracking user actions)
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False

    # Celery logger
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.INFO)
    celery_logger.addHandler(app_handler)
    celery_logger.addHandler(error_handler)
    celery_logger.propagate = False

    return {
        'app': logging.getLogger('smartcare'),
        'request_response': logging.getLogger('request_response'),
        'audit': logging.getLogger('audit'),
        'performance': logging.getLogger('django.db.backends'),
    }


# Create logger instances
def get_logger(name='smartcare'):
    """Get a logger instance."""
    return logging.getLogger(name)


def get_audit_logger():
    """Get the audit logger."""
    return logging.getLogger('audit')


def get_request_logger():
    """Get the request/response logger."""
    return logging.getLogger('request_response')
