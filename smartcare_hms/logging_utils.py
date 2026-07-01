"""
Utility functions for logging throughout the application.

Provides convenient logging functions for common scenarios:
- Error logging with context
- Audit logging for user actions
- Performance logging
- Security event logging
"""

import logging
import json
from functools import wraps
import time


def get_logger(name='smartcare'):
    """Get a logger instance."""
    return logging.getLogger(name)


def get_audit_logger():
    """Get the audit logger."""
    return logging.getLogger('audit')


def get_request_logger():
    """Get the request/response logger."""
    return logging.getLogger('request_response')


def log_audit_event(action, resource, resource_id, user_id=None, tenant_id=None,
                    status='success', details=None, **kwargs):
    """
    Log an audit event.

    Args:
        action: Action performed (e.g., 'CREATE', 'UPDATE', 'DELETE')
        resource: Resource type (e.g., 'Patient', 'User')
        resource_id: ID of the resource
        user_id: User who performed the action
        tenant_id: Tenant ID
        status: Status of the action ('success' or 'failure')
        details: Additional details as dict
        **kwargs: Additional fields to log
    """
    audit_logger = get_audit_logger()

    audit_log = {
        'action': action,
        'resource': resource,
        'resource_id': resource_id,
        'user_id': user_id,
        'tenant_id': tenant_id,
        'status': status,
        'details': details or {},
    }
    audit_log.update(kwargs)

    audit_logger.info(json.dumps(audit_log))


def log_error(message, exception=None, context=None, **kwargs):
    """
    Log an error with context.

    Args:
        message: Error message
        exception: Exception object if applicable
        context: Contextual information
        **kwargs: Additional fields to log
    """
    logger = get_logger()

    error_log = {
        'message': message,
        'context': context or {},
    }
    error_log.update(kwargs)

    if exception:
        logger.error(json.dumps(error_log), exc_info=True)
    else:
        logger.error(json.dumps(error_log))


def log_security_event(event_type, user_id=None, tenant_id=None, 
                      status='success', details=None, **kwargs):
    """
    Log a security event.

    Args:
        event_type: Type of security event (e.g., 'LOGIN_ATTEMPT', 'PERMISSION_DENIED')
        user_id: User ID
        tenant_id: Tenant ID
        status: Status of the event
        details: Additional details
        **kwargs: Additional fields
    """
    logger = logging.getLogger('django.security')

    security_log = {
        'event_type': event_type,
        'user_id': user_id,
        'tenant_id': tenant_id,
        'status': status,
        'details': details or {},
    }
    security_log.update(kwargs)

    logger.info(json.dumps(security_log))


def log_performance(operation, duration_ms, success=True, context=None, **kwargs):
    """
    Log performance metrics.

    Args:
        operation: Name of the operation
        duration_ms: Duration in milliseconds
        success: Whether the operation succeeded
        context: Contextual information
        **kwargs: Additional fields
    """
    logger = logging.getLogger('django.db.backends')

    perf_log = {
        'operation': operation,
        'duration_ms': round(duration_ms, 2),
        'success': success,
        'context': context or {},
    }
    perf_log.update(kwargs)

    if duration_ms > 1000:  # Log slow operations as warning
        logger.warning(json.dumps(perf_log))
    else:
        logger.debug(json.dumps(perf_log))


def log_task_execution(task_name, status, duration_ms=None, 
                      result=None, error=None, **kwargs):
    """
    Log asynchronous task execution (Celery, etc).

    Args:
        task_name: Name of the task
        status: Status ('started', 'completed', 'failed')
        duration_ms: Duration in milliseconds
        result: Task result
        error: Error message if failed
        **kwargs: Additional fields
    """
    logger = logging.getLogger('celery')

    task_log = {
        'task_name': task_name,
        'status': status,
        'duration_ms': duration_ms,
        'result': result,
        'error': error,
    }
    task_log.update(kwargs)

    if status == 'failed':
        logger.error(json.dumps(task_log))
    else:
        logger.info(json.dumps(task_log))


class LogExecutionTime:
    """
    Context manager and decorator to log function execution time.

    Usage:
        # As context manager
        with LogExecutionTime('expensive_operation'):
            do_something()

        # As decorator
        @LogExecutionTime('my_function')
        def my_function():
            pass
    """

    def __init__(self, operation_name, logger=None):
        self.operation_name = operation_name
        self.logger = logger or get_logger()
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        success = exc_type is None

        log_performance(
            self.operation_name,
            duration_ms,
            success=success,
        )

        if exc_type is not None:
            self.logger.error(f"Operation '{self.operation_name}' failed: {exc_val}", exc_info=True)

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper


class StructuredLogger:
    """
    Helper class for structured logging in your application.

    Usage:
        logger = StructuredLogger('my_module')
        logger.info('User logged in', user_id=123, tenant_id=456)
        logger.error('Payment failed', user_id=123, error='Card declined')
    """

    def __init__(self, module_name='smartcare'):
        self.logger = get_logger(module_name)

    def info(self, message, **context):
        """Log info message with context."""
        log_data = {'message': message, **context}
        self.logger.info(json.dumps(log_data))

    def warning(self, message, **context):
        """Log warning message with context."""
        log_data = {'message': message, **context}
        self.logger.warning(json.dumps(log_data))

    def error(self, message, exception=None, **context):
        """Log error message with context."""
        log_data = {'message': message, **context}
        if exception:
            self.logger.error(json.dumps(log_data), exc_info=True)
        else:
            self.logger.error(json.dumps(log_data))

    def debug(self, message, **context):
        """Log debug message with context."""
        log_data = {'message': message, **context}
        self.logger.debug(json.dumps(log_data))


# Create a default structured logger for easy import and use
logger = StructuredLogger()
