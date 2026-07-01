# Quick Start Guide - Enterprise Logging for SmartCare HMS

## 5-Minute Setup

### 1. Install Dependencies
```bash
cd HMS_backend
pip install python-json-logger==2.0.7
# Already in requirements.txt, so you can also run:
pip install -r requirements.txt
```

### 2. Verify Configuration
The logging is automatically configured in `smartcare_hms/settings.py`. No additional setup needed!

### 3. Start Your Application
```bash
python manage.py runserver
```

### 4. Check Logs
```bash
# View application logs
tail -f logs/app.log

# View errors
tail -f logs/error.log

# View requests
tail -f logs/requests.log

# View audit trail
tail -f logs/audit.log
```

## Common Usage Patterns

### Log User Actions
```python
from smartcare_hms.logging_utils import log_audit_event

log_audit_event(
    action='CREATE',
    resource='Patient',
    resource_id=patient_id,
    user_id=request.user.id,
    tenant_id=request.tenant.id,
    details={'name': 'John Doe', 'email': 'john@example.com'}
)
```

### Log Errors
```python
from smartcare_hms.logging_utils import logger

try:
    process_payment()
except Exception as e:
    logger.error('Payment failed', exception=e, user_id=user_id)
```

### Track Performance
```python
from smartcare_hms.logging_utils import LogExecutionTime

with LogExecutionTime('expensive_operation'):
    result = expensive_function()
```

### Security Events
```python
from smartcare_hms.logging_utils import log_security_event

log_security_event(
    event_type='LOGIN_ATTEMPT',
    user_id=user_id,
    status='success',
    ip_address=request.META.get('REMOTE_ADDR')
)
```

## File Structure

```
HMS_backend/
├── smartcare_hms/
│   ├── logging_config.py          # Main logging configuration
│   ├── logging_middleware.py       # Request/response logging
│   ├── logging_utils.py           # Utility functions
│   └── settings.py                # Updated with logging setup
├── logs/                          # Log files (auto-created)
│   ├── app.log
│   ├── error.log
│   ├── requests.log
│   ├── audit.log
│   └── performance.log
├── LOGGING_GUIDE.md               # Comprehensive documentation
└── LOGGING_EXAMPLES.md            # Code examples
```

## Log Output Examples

### Console (Development)
```
2024-01-15 10:30:45 - INFO - smartcare - Patient created successfully
2024-01-15 10:30:46 - WARNING - django.db.backends - Slow query detected: 1250ms
2024-01-15 10:30:47 - ERROR - smartcare - Payment failed
```

### Files (JSON Format)
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "INFO",
  "name": "smartcare",
  "message": "Patient created successfully",
  "request_id": "a1b2c3d4-e5f6-47f8-a9b0-c1d2e3f4a5b6",
  "user_id": 123,
  "tenant_id": 456,
  "hostname": "localhost",
  "environment": "development"
}
```

## Integration with Your Apps

### Step 1: Import in Your View
```python
# patients/views.py
from smartcare_hms.logging_utils import logger, log_audit_event
```

### Step 2: Add Logging to Methods
```python
def create_patient(request):
    try:
        patient = Patient.objects.create(**request.data)
        log_audit_event(
            action='CREATE',
            resource='Patient',
            resource_id=patient.id,
            user_id=request.user.id
        )
        return Response({'success': True})
    except Exception as e:
        logger.error('Failed to create patient', exception=e)
        raise
```

### Step 3: That's It!
Your logs will automatically include:
- Timestamps
- Request correlation IDs
- User IDs
- Tenant IDs
- IP addresses
- Request duration
- All in JSON format for easy parsing

## Monitoring & Debugging

### Check Request Correlation
Every request gets a unique ID. Use it to trace through logs:

```bash
# Find all logs for a specific request
grep "a1b2c3d4-e5f6" logs/*.log
```

### Identify Slow Queries
```bash
# Find slow operations (>1 second)
grep "slow_request" logs/requests.log

# Find database queries >1 second
grep "duration_ms" logs/performance.log | grep -v "duration_ms.*[0-9]$"
```

### Audit Trail
```bash
# View all user actions
tail logs/audit.log

# Filter by action
grep '"action":"DELETE"' logs/audit.log

# Filter by user
grep '"user_id":123' logs/audit.log
```

## Troubleshooting

### No Logs Appearing
1. Check `logs/` directory exists
2. Ensure write permissions: `chmod 755 logs/`
3. Check console for errors: `python manage.py runserver`

### Logs Rotate Too Quickly
- Logs rotate at 10MB by default
- Edit `logging_config.py` to change: `maxBytes=52428800` (50MB)

### Performance Issues
- JSON formatting adds ~10-15% overhead
- This is normal for enterprise logging
- Consider async logging for high-volume apps

## Next Steps

1. **Review full documentation**: Read `LOGGING_GUIDE.md`
2. **See code examples**: Check `LOGGING_EXAMPLES.md`
3. **Integrate into your apps**:
   - Add logging to views
   - Add audit logging to models
   - Add performance tracking to heavy operations
4. **Set up monitoring**:
   - ELK Stack for centralized logging
   - Sentry for error tracking
   - CloudWatch for cloud deployments

## Support

- **Documentation**: `LOGGING_GUIDE.md`
- **Examples**: `LOGGING_EXAMPLES.md`
- **Config**: `smartcare_hms/logging_config.py`
- **Utils**: `smartcare_hms/logging_utils.py`
- **Middleware**: `smartcare_hms/logging_middleware.py`

---

Happy logging! 🎯
