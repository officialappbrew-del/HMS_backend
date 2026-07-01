# Enterprise-Grade Logging System for SmartCare HMS

## Overview

This is a production-grade logging system designed for enterprise applications. It provides comprehensive logging capabilities including structured JSON logging, request tracing, audit logging, and performance monitoring.

## Features

### 1. **Structured JSON Logging**
- All logs are in JSON format for easy parsing and analysis
- Includes contextual information: correlation IDs, user IDs, tenant IDs, timestamps
- Compatible with log aggregation services (ELK, Splunk, DataDog, CloudWatch)

### 2. **Multiple Log Channels**
- **app.log**: General application logs
- **error.log**: Error and critical messages
- **requests.log**: HTTP request/response details
- **audit.log**: User actions and compliance tracking
- **performance.log**: Database query times and slow operations

### 3. **Rotating File Handlers**
- Automatic log rotation to prevent disk space issues
- Configurable size limits and retention
- Default: 10MB per file, 20 backups retained

### 4. **Request Correlation**
- Unique correlation IDs for tracing requests through the system
- Included in all log entries during request processing
- Passed to external services and async tasks

### 5. **Multi-Tenant Support**
- Automatic tenant ID capture and logging
- Supports both header-based (`X-Tenant-ID`) and middleware-based tenant resolution

### 6. **Performance Monitoring**
- Automatic slow query detection (>1s logged as warnings)
- Database query logging in debug mode
- Execution time tracking for operations

### 7. **Security & Audit**
- Dedicated audit logger for compliance tracking
- Security event logging
- User action tracking with context

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The following package is required (already added to requirements.txt):
```
python-json-logger==2.0.7
```

### 2. Configuration

The logging is automatically configured in `smartcare_hms/settings.py`:

```python
from .logging_config import setup_logging

# Initialize logging
setup_logging(BASE_DIR, debug=DEBUG)
```

Middleware is automatically added in the MIDDLEWARE list:
```python
MIDDLEWARE = [
    # ... other middleware ...
    'smartcare_hms.logging_middleware.CorrelationIdMiddleware',
    'smartcare_hms.logging_middleware.EnrichLoggingContextMiddleware',
    'smartcare_hms.logging_middleware.RequestResponseLoggingMiddleware',
]
```

## Usage

### 1. Basic Logging

```python
from smartcare_hms.logging_utils import logger, get_logger

# Using structured logger
logger.info('User logged in', user_id=123, tenant_id=456)
logger.error('Payment processing failed', user_id=123, error='Card declined')

# Or get specific logger
app_logger = get_logger('smartcare')
app_logger.info('Processing patient appointment')
```

### 2. Audit Logging

Track user actions for compliance:

```python
from smartcare_hms.logging_utils import log_audit_event

# Log when user creates a resource
log_audit_event(
    action='CREATE',
    resource='Patient',
    resource_id=patient_id,
    user_id=request.user.id,
    tenant_id=request.tenant.id,
    status='success',
    details={'first_name': 'John', 'last_name': 'Doe'}
)

# Log when user updates a resource
log_audit_event(
    action='UPDATE',
    resource='Patient',
    resource_id=patient_id,
    user_id=request.user.id,
    tenant_id=request.tenant.id,
    status='success',
    details={'field': 'phone_number', 'old_value': '080...', 'new_value': '090...'}
)
```

### 3. Error Logging with Context

```python
from smartcare_hms.logging_utils import log_error

try:
    result = process_payment(patient_id)
except PaymentException as e:
    log_error(
        'Payment processing failed',
        exception=e,
        context={'patient_id': patient_id, 'amount': 5000}
    )
```

### 4. Security Event Logging

```python
from smartcare_hms.logging_utils import log_security_event

# Log login attempt
log_security_event(
    event_type='LOGIN_ATTEMPT',
    user_id=user_id,
    tenant_id=tenant_id,
    status='success'
)

# Log permission denied
log_security_event(
    event_type='PERMISSION_DENIED',
    user_id=user_id,
    tenant_id=tenant_id,
    resource='patient_records',
    status='failure'
)
```

### 5. Performance Logging

```python
from smartcare_hms.logging_utils import log_performance

# Log operation performance
start = time.time()
result = expensive_operation()
duration_ms = (time.time() - start) * 1000
log_performance('expensive_operation', duration_ms, success=True)

# Using context manager
from smartcare_hms.logging_utils import LogExecutionTime

with LogExecutionTime('data_processing'):
    process_large_dataset()

# Using decorator
@LogExecutionTime('calculate_patient_stats')
def calculate_patient_statistics():
    # calculation logic
    pass
```

### 6. Request/Response Logging

Request/response logging is automatic via middleware. Each request generates:
- Request log: method, path, user, tenant, IP address
- Response log: status code, duration, user, tenant

Example log entry (JSON):
```json
{
  "event": "request_completed",
  "method": "POST",
  "path": "/api/patients/",
  "status_code": 201,
  "duration_ms": 245.32,
  "user_id": 123,
  "tenant_id": 456,
  "ip_address": "192.168.1.1",
  "timestamp": "2024-01-15T10:30:45.123456",
  "hostname": "app-server-01",
  "environment": "production"
}
```

### 7. Celery Task Logging

```python
from smartcare_hms.logging_utils import log_task_execution
import time

@celery_app.task
def send_appointment_reminder(appointment_id):
    start = time.time()
    try:
        # Send reminder logic
        send_sms_reminder(appointment_id)
        duration_ms = (time.time() - start) * 1000
        
        log_task_execution(
            task_name='send_appointment_reminder',
            status='completed',
            duration_ms=duration_ms,
            result={'appointment_id': appointment_id, 'sent': True}
        )
    except Exception as e:
        log_task_execution(
            task_name='send_appointment_reminder',
            status='failed',
            error=str(e)
        )
        raise
```

## Log Files Location

All logs are stored in: `HMS_backend/logs/`

```
logs/
├── app.log              # General application logs (rotated)
├── app.log.1            # Rotated backup
├── app.log.2
├── error.log            # Errors and critical messages (rotated)
├── error.log.1
├── error.log.2
├── requests.log         # HTTP requests (rotated)
├── requests.log.1
├── audit.log            # Audit trail (rotated)
├── performance.log      # Slow queries and performance (rotated)
└── performance.log.1
```

## Log Format

### Console Output (Development)
```
2024-01-15 10:30:45 - INFO - smartcare - User logged in
```

### JSON File Output (Production)
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "INFO",
  "name": "smartcare",
  "message": "User logged in",
  "request_id": "a1b2c3d4-e5f6-47f8-a9b0-c1d2e3f4a5b6",
  "user_id": 123,
  "tenant_id": 456,
  "method": "POST",
  "path": "/api/auth/login/",
  "ip_address": "192.168.1.1",
  "hostname": "app-server-01",
  "environment": "production"
}
```

## Integration with Monitoring Tools

### 1. ELK Stack (Elasticsearch, Logstash, Kibana)

The JSON format is compatible with Logstash. Configure Logstash to:
```
input {
  file {
    path => "/path/to/logs/app.log"
    codec => json
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "smartcare-hms-%{+YYYY.MM.dd}"
  }
}
```

### 2. Sentry Integration

For error tracking with Sentry, update settings.py:

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
    environment=os.getenv('ENVIRONMENT', 'development')
)
```

### 3. CloudWatch Integration

```python
import watchtower

cloudwatch_handler = watchtower.CloudWatchLogHandler(
    log_group='smartcare-hms',
    stream_name='app-logs',
    boto3_client=boto3.client('logs', region_name='us-east-1')
)
```

## Best Practices

### 1. Use Structured Logging
```python
# Good
logger.info('Patient record created', patient_id=123, user_id=456, duration_ms=150)

# Avoid
logger.info(f'Patient record created with ID {patient_id}')
```

### 2. Include Context
```python
# Always include relevant context
log_audit_event(
    action='UPDATE',
    resource='Patient',
    resource_id=patient_id,
    user_id=request.user.id,
    tenant_id=request.tenant.id
)
```

### 3. Use Appropriate Log Levels
- **DEBUG**: Detailed diagnostic information (development only)
- **INFO**: Confirmation that things are working (user actions, state changes)
- **WARNING**: Warning messages (slow queries >1s, deprecated API usage)
- **ERROR**: Error events (exceptions, failed operations)
- **CRITICAL**: Serious error events (system failures)

### 4. Avoid Logging Sensitive Data
```python
# Bad
logger.info(f'User logged in: {password}')

# Good
logger.info('User logged in', user_id=user_id)
```

### 5. Use Request Correlation IDs
```python
# Correlation ID is automatically added from middleware
# Access it if needed:
correlation_id = request.correlation_id
logger.info('Processing request', correlation_id=correlation_id)
```

## Troubleshooting

### Logs Not Appearing
1. Check that `LOG_DIR` exists: `logs/` directory
2. Verify permissions on log files: `chmod 755 logs/`
3. Check console output for configuration errors
4. Ensure `setup_logging()` is called in settings.py

### Log Files Growing Too Large
- Log rotation is automatic at 10MB per file
- Check `performance.log` for excessive database logging
- In production, disable DEBUG to reduce console logging

### Performance Impact
- JSON formatting adds ~10-15% overhead
- Rotating handlers are efficient and non-blocking
- Async logging can be enabled for high-volume applications

## Configuration Options

Edit `smartcare_hms/logging_config.py` to customize:

```python
# Change log file sizes
app_handler = RotatingFileHandlerWithJSON(
    str(app_log_file),
    maxBytes=52428800,  # 50 MB (increase for high-volume)
    backupCount=50,     # Keep more backups
)

# Change log levels
django_db_logger.setLevel(logging.DEBUG if debug else logging.ERROR)  # Less verbose

# Add new loggers
custom_logger = logging.getLogger('custom_module')
custom_logger.addHandler(app_handler)
```

## Example Django App Integration

In your Django app views or models:

```python
# users/views.py
from smartcare_hms.logging_utils import logger, get_audit_logger, log_security_event

class LoginView(APIView):
    def post(self, request):
        try:
            user = authenticate(username=username, password=password)
            if user:
                log_security_event('LOGIN_ATTEMPT', user_id=user.id, status='success')
                logger.info('User logged in', user_id=user.id, tenant_id=request.tenant.id)
                return Response({'token': token})
            else:
                log_security_event('LOGIN_ATTEMPT', username=username, status='failure')
                logger.warning('Failed login attempt', username=username)
                return Response({'error': 'Invalid credentials'}, status=401)
        except Exception as e:
            logger.error('Login error', exception=e)
            raise

# patients/models.py
from smartcare_hms.logging_utils import log_audit_event

class Patient(models.Model):
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            log_audit_event(
                action='CREATE',
                resource='Patient',
                resource_id=self.pk,
                details={'name': self.name, 'email': self.email}
            )
```

## Performance Metrics

Typical logging overhead:
- **Console logging**: <1ms per log entry
- **File rotation**: <5ms (on rotation event)
- **JSON formatting**: ~10-15% overhead vs plain text
- **Memory usage**: ~2-5MB for typical Django app

For high-volume applications, consider:
- Using async handlers
- Buffering log entries
- Sampling for non-critical events
- Separate logging server

## Support & Maintenance

For issues or improvements:
1. Check log files in `logs/` directory
2. Review this documentation
3. Enable DEBUG mode for detailed logging
4. Check Django/DRF documentation for specific errors

---

**Last Updated**: January 2024
**Version**: 1.0.0
