# Tenant-Specific Email Configuration Guide

## Overview

The HMS system now supports **per-tenant email configuration**, allowing each hospital/clinic to use their own email credentials for sending notifications, appointments reminders, and patient communications. This replaces the global email configuration with tenant-specific settings.

## Architecture

### Components

1. **Frontend Configuration** (`HMS_React/src/pages/Settings.jsx`)
   - Communication settings form for tenant admins
   - Configure SMTP credentials, sender email, and sender name

2. **Backend Communication Module** (`tenants/communication.py`)
   - Resolves tenant-specific email identity at send-time
   - Provides utility function for sending emails with tenant config
   - Falls back to global Django settings if tenant config is incomplete

3. **Database Model** (`tenants/models.py`)
   - `CommunicationProfile`: Stores per-tenant email configuration
   - Encrypted password storage for security
   - SMS configuration (separate channel)

## Configuration Fields

When a tenant admin goes to Settings → Communication, they can configure:

| Field | Description | Type |
|-------|-------------|------|
| `email_enabled` | Enable/disable email notifications | Boolean |
| `email_from` | Sender email address | Email |
| `from_name` | Sender display name (shows in "From" field) | String |
| `email_provider` | Email provider (gmail, sendgrid, custom, etc.) | String |
| `email_host` | SMTP server address | String |
| `email_port` | SMTP port | Integer (default: 587) |
| `email_username` | SMTP authentication username | String |
| `email_password` | SMTP authentication password (encrypted) | String |
| `email_use_tls` | Use TLS encryption | Boolean |
| `reply_to` | Reply-to email address | Email |
| `verified_domain` | SPF/DKIM verified domain | String |

## How It Works

### Email Resolution Flow

```
Patient/Doctor sends appointment request
    ↓
Appointment reminder needs to be sent
    ↓
_dispatch_appointment_reminder() called
    ↓
resolve_email_identity(tenant) retrieves:
  - Tenant's SMTP config (if set in Settings)
  - Falls back to global Django EMAIL_* settings
  - Falls back to DEFAULT_FROM_EMAIL if needed
    ↓
send_tenant_email() sends using tenant credentials
    ↓
Email delivered from tenant's configured sender
```

## Usage Guide

### Basic Email Sending

```python
from tenants.communication import send_tenant_email

# Send a simple email
send_tenant_email(
    tenant=my_tenant,
    subject='Appointment Reminder',
    message='Your appointment is scheduled for tomorrow at 2 PM',
    recipient_list=['patient@example.com'],
)
```

### Email with HTML Content

```python
from tenants.communication import send_tenant_email

html_message = """
<html>
  <body>
    <h2>Appointment Reminder</h2>
    <p>Your appointment is scheduled for <strong>tomorrow at 2 PM</strong></p>
  </body>
</html>
"""

send_tenant_email(
    tenant=my_tenant,
    subject='Appointment Reminder',
    message='Your appointment is scheduled for tomorrow at 2 PM',
    recipient_list=['patient@example.com'],
    html_message=html_message,
)
```

### Email with Tenant Branding

```python
from tenants.communication import send_tenant_email, build_email_context

# Build context with tenant branding
context = build_email_context(
    tenant=my_tenant,
    extra={
        'patient_name': 'John Doe',
        'appointment_date': '2024-01-15',
        'appointment_time': '2:00 PM',
    }
)

# Use context in template
html_message = """
<html>
  <body>
    <h1>{{ tenant_name }}</h1>
    <img src="{{ tenant_logo_url }}" alt="{{ tenant_name }}">
    <h2>Appointment Reminder</h2>
    <p>Dear {{ patient_name }},</p>
    <p>Your appointment is scheduled for {{ appointment_date }} at {{ appointment_time }}</p>
    <p>&copy; {{ year }} {{ tenant_name }}</p>
  </body>
</html>
"""

# Render template with context (using Django template engine)
from django.template.loader import render_to_string
rendered_html = render_to_string('path/to/template.html', context)

send_tenant_email(
    tenant=my_tenant,
    subject='Appointment Reminder',
    message='Your appointment is scheduled...',
    recipient_list=['patient@example.com'],
    html_message=rendered_html,
)
```

### Getting Tenant Email Identity

```python
from tenants.communication import resolve_email_identity

# Get full tenant email configuration
identity = resolve_email_identity(tenant)

print(f"From Email: {identity['from_email']}")
print(f"From Name: {identity['from_name']}")
print(f"SMTP Host: {identity['host']}")
print(f"SMTP Port: {identity['port']}")
print(f"Use TLS: {identity['use_tls']}")
```

## Current Implementations

### ✅ Appointment Reminders
**File:** `patients/views.py`
**Function:** `_dispatch_appointment_reminder()`
**Status:** Updated to use tenant email configuration

```python
# Now uses tenant-specific email configuration
from tenants.communication import send_tenant_email

send_tenant_email(
    tenant=appointment.tenant,
    subject='Appointment Reminder',
    message=reminder_message,
    recipient_list=[patient.email],
)
```

### ✅ Password Reset
**File:** `users/tasks.py`
**Function:** `send_password_reset_email_task()`
**Status:** Already uses tenant configuration via `resolve_email_identity()`

### ✅ Staff Welcome Emails
**File:** `tenants/tasks.py`
**Function:** `send_staff_welcome_email()`
**Status:** Already uses tenant configuration

### ✅ Tenant Welcome Emails
**File:** `users/tasks.py`, `superadmin/views.py`
**Status:** Already uses tenant configuration

### ✅ Subscription Expiry Notifications
**File:** `tenants/tasks.py`
**Function:** `send_subscription_expiry_notifications()`
**Status:** Already uses tenant configuration

## Implementing for New Features

When adding new email notifications, follow this pattern:

### 1. Import the utility function
```python
from tenants.communication import send_tenant_email, build_email_context
```

### 2. Build email context with tenant branding
```python
context = build_email_context(
    tenant=tenant_instance,
    extra={'custom_field': 'value'}
)
```

### 3. Render email template
```python
from django.template.loader import render_to_string

html_message = render_to_string('path/to/template.html', context)
```

### 4. Send using tenant configuration
```python
send_tenant_email(
    tenant=tenant_instance,
    subject='Email Subject',
    message='Plain text version',
    recipient_list=['recipient@example.com'],
    html_message=html_message,
)
```

## Fallback Behavior

If a tenant hasn't configured email settings, the system falls back to:

1. **Tenant-configured settings** (if set)
2. **Django global settings** (EMAIL_HOST, EMAIL_PORT, etc.)
3. **DEFAULT_FROM_EMAIL** (last resort)

This ensures backward compatibility - existing systems continue to work without changes.

## Security Considerations

1. **Password Encryption**: SMTP passwords are encrypted in the database
2. **Validation**: Email addresses are validated before sending
3. **Rate Limiting**: Consider implementing email rate limits per tenant
4. **Audit Logging**: Email sending is logged for audit trails
5. **SPF/DKIM**: Tenants should verify their domain for better deliverability

## Troubleshooting

### Emails not sending
1. Check if tenant has email enabled in Settings → Communication
2. Verify SMTP credentials in tenant's communication profile
3. Check server logs: `tail -f logs/emails.log`
4. Verify firewall/network access to SMTP server

### Emails sent from wrong sender
1. Check tenant's `email_from` setting in Communication settings
2. Verify global Django EMAIL_HOST_USER if tenant config is empty
3. Check email headers in recipient's inbox

### SMTP Authentication Failed
1. Verify username/password in tenant's communication profile
2. For Gmail, use App Passwords (not regular password)
3. Check if 2FA is enabled on email account
4. Verify IP allowlisting on email provider

## Email Templates

Email templates should be stored in `templates/` directory and use tenant context:

```django
{% extends "emails/base_email.html" %}

{% block title %}Email Title{% endblock %}
{% block subtitle %}Subtitle{% endblock %}

{% block body %}
  {% if tenant_logo_url %}
    <img src="{{ tenant_logo_url }}" alt="{{ tenant_name }}">
  {% endif %}
  
  <h2>Hello {{ patient_name }},</h2>
  <p>{{ message_body }}</p>
  
  <p>&copy; {{ year }} {{ tenant_name }}</p>
{% endblock %}
```

## API Endpoints

### Get Communication Profile
```
GET /api/v1/tenants/communication-profile/current/
```

### Update Communication Profile
```
PUT /api/v1/tenants/communication-profile/current/
PATCH /api/v1/tenants/communication-profile/current/
```

### List All Communication Profiles (admins only)
```
GET /api/v1/tenants/communication-profile/
```

## Testing

### In Development
```python
# Use console email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### With Test Tenant
```python
from tenants.models import Tenant
from tenants.communication import send_tenant_email

tenant = Tenant.objects.first()
send_tenant_email(
    tenant=tenant,
    subject='Test Email',
    message='This is a test',
    recipient_list=['test@example.com'],
)
```

## Migration Guide

### For Existing Systems
No migrations needed! The `CommunicationProfile` model already exists. Existing systems will:
1. Continue using global EMAIL_* settings
2. Gradually adopt tenant configuration as admins set it up
3. Have full backward compatibility

### For New Implementations
1. Configure global EMAIL_* settings as fallback
2. Instruct tenant admins to configure email in Settings
3. All new emails will automatically use tenant configuration

## Future Enhancements

- [ ] Email template customization per tenant
- [ ] Email sending analytics and tracking
- [ ] Batch email processing
- [ ] Email scheduling
- [ ] Multiple email configuration per tenant
- [ ] SMS gateway configuration (similar pattern)
- [ ] WhatsApp notification support
- [ ] Email signature templates

## Support

For issues or questions:
1. Check logs: `tail -f logs/errors.log`
2. Review tenant communication profile: `/admin/tenants/communicationprofile/`
3. Verify SMTP credentials with your email provider
4. Test with a simple email first before adding templates
