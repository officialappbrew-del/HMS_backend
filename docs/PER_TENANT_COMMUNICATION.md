# Per-Tenant Communication Identity

## Goal

Give every tenant (hospital) its own unique sender identity for email and SMS so hospitals don't share a single global sender for patient/staff communication. Follows the industry-standard per-tenant subaccount / sender identity model.

## Architecture

### Core Principle

Every tenant gets its own unique sender identity for both email and SMS/phone. Different tenants cannot share a single "from" address or phone number because:

- **Deliverability & reputation** — one tenant spamming or getting flagged would poison the shared sender identity for all other hospitals.
- **Compliance** — SMS/phone carriers and email providers require the sender to be identifiable and verified per entity.
- **Branding & trust** — patients should see their hospital's name/number, not a generic central one.
- **Legal/regulatory** — TCPA, CTIA, GDPR, and telecom rules tie consent and opt-out obligations to a specific sender.

## Implementation

### 1. CommunicationProfile Model

Location: `tenants/models.py`

A `OneToOne` relationship with `Tenant` that stores:

- **Email identity**: `email_from`, `from_name`, `reply_to`, `verified_domain`, `email_provider`, SMTP credentials
- **SMS identity**: `sms_provider`, `sms_sender_id`, `sms_phone_number`, `sms_api_key`, `sms_country_code`
- **Compliance**: `consent_tracking_enabled`, `opt_out_message`, `dnd_enabled`, `message_templates` (JSON)
- **Channel toggles & limits**: `email_enabled`, `sms_enabled`, `daily_email_limit`, `daily_sms_limit`

Auto-created on tenant creation in `tenants/serializers.py` → `TenantSerializer.create()`.

### 2. Database Router

Location: `tenants/db_router.py`

`CommunicationProfile` is registered in `tenant_models` so it routes to the correct tenant schema.

### 3. Routing Service

Location: `tenants/communication.py`

Provides helper functions:

- `get_communication_profile(tenant)` — returns profile, creating default if missing
- `resolve_email_identity(tenant)` — returns dict with `from_email`, `from_name`, `reply_to`, SMTP settings, falling back to global Django settings
- `resolve_sms_identity(tenant)` — returns dict with `provider`, `sender_id`, `phone_number`, `api_key`, `country_code`
- `is_email_enabled(tenant)` / `is_sms_enabled(tenant)` — channel toggle checks
- `get_message_template(tenant, channel, message_type)` — retrieves pre-approved templates

### 4. API Endpoints

Location: `tenants/urls.py`, `tenants/views.py`

`CommunicationProfileViewSet` registered at `/api/v1/tenants/communication-profile/`

- Standard CRUD for root admins / system admins
- `GET /api/v1/tenants/communication-profile/current/` — returns the current user's tenant profile

### 5. Admin Interface

Location: `tenants/admin.py`

`CommunicationProfileAdmin` registered with fieldsets for email identity, SMTP credentials, SMS identity, compliance, and channel limits.

### 6. Email Task Integration

Location: `users/tasks.py`

`send_password_reset_email_task` now attempts to resolve the tenant's email identity via `tenants.communication.resolve_email_identity()`. If a tenant-specific identity is configured, it uses that `from_email`/`from_name`. Otherwise, it falls back to `settings.DEFAULT_FROM_EMAIL`.

### 7. Branded Email Templates

Location: `templates/emails/base_email.html`, `templates/users/`

Outbound emails render through a shared, responsive HTML base layout (`emails/base_email.html`) that dynamically injects the tenant's **logo** (`tenant_logo_url`) and **name** (`tenant_name`) in the header and footer. Individual email bodies (e.g., `users/password_reset_email.html`) extend the base via template inheritance.

The brand context is built by `tenants.communication.build_email_context(tenant, extra=None, request=None)`, which returns:

- `tenant_name` — the hospital's display name
- `tenant_logo_url` — absolute URL of `tenant.logo` (empty when no logo / no host available in background tasks)
- `year` — current year for the footer

Because background Celery tasks have no `request`, the logo URL is only emitted when `MEDIA_URL` is absolute (S3/Supabase remote storage). For local/media-relative setups the hospital name still renders as text, so branding is preserved even when email clients block remote images.

To apply the same branding to any new email, extend `emails/base_email.html` and pass the tenant through `build_email_context()`.

## Provider Recommendations

### Email

- **SendGrid** — subaccounts, dedicated IP pools, webhooks, template engine
- **AWS SES** — subaccounts via AWS Organizations, dedicated IPs, DKIM/SPF per domain
- **Mailgun** — subaccounts, dedicated IPs, SMTP/API
- **SMTP** — direct SMTP credentials per tenant (least recommended for production)

### SMS

- **Twilio** — subaccounts, 10DLC, alphanumeric sender IDs, toll-free numbers
- **MessageBird** — similar subaccount model, strong EU/Africa coverage
- **Vonage** — similar subaccount model

## Security Notes

- Credentials are stored as `CharField` in the database. For production, consider:
  - `django-cryptography` `EncryptedJSONField` / `EncryptedCharField`
  - Or store actual API keys in a secrets manager (AWS Secrets Manager, HashiCorp Vault) and reference them by ID in the profile
- The `message_templates` JSON field stores pre-approved content; validate against carrier requirements per region
- Audit log all sends per tenant for compliance

## Setup Checklist

1. Configure provider subaccounts for each tenant
2. Verify sending domains / phone numbers per tenant
3. Set SPF/DKIM/DMARC for email domains
4. Pre-approve SMS message templates where required (10DLC, etc.)
5. Populate `CommunicationProfile` for each tenant via API or admin
6. Test send flow end-to-end for a sample tenant

## Testing

```bash
python manage.py makemigrations tenants
python manage.py migrate
python manage.py createsuperuser
```

Then in Django admin or via API:

```bash
# Create tenant (profile auto-created)
curl -X POST http://localhost:8000/api/v1/tenants/tenants/ -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name": "Test Hospital", "domain": "test.example.com", ...}'

# Read current communication profile
curl http://localhost:8000/api/v1/tenants/communication-profile/current/ -H "Authorization: Bearer <token>"
```
