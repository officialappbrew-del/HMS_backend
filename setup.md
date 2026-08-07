# SmartCare HMS quick setup

Use this file as the only setup guide.

## 1) Install and run

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

### Initialize the base tenant data

On Windows PowerShell, use one of these methods:

```powershell
python manage.py shell
```

Then inside the shell run:

```python
exec(open('tenants_setup.py').read())
```

Or use a one-line command:

```powershell
python -c "exec(open('tenants_setup.py').read())"
```

> Do not use `python manage.py shell < tenants_setup.py` in PowerShell because `<` is not supported for redirection there.

## 2) API base URLs

- Global/system login: http://localhost:8000/api/v1/auth/login/
- Tenant staff login (with tenant context): http://localhost:8000/api/v1/auth/login/
- Patient login: http://localhost:8000/api/v1/patients/login/
- Tenant list/create: http://localhost:8000/api/v1/tenants/tenants/
- Tenant root admin create: http://localhost:8000/api/v1/tenants/tenants/{tenant_id}/create-root-admin/
- Tenant users: http://localhost:8000/api/v1/tenants/users/
- Communication profile: http://localhost:8000/api/v1/tenants/communication-profile/
- Swagger docs: http://localhost:8000/swagger/

## 3) Tenant setup flow

1. Create the global/system admin with `createsuperuser`.
2. Run the tenant setup script once using one of the PowerShell-safe methods above.
3. Create a tenant using the system admin.

### Create a tenant

Use this endpoint:

```http
POST /api/v1/tenants/tenants/
```

Example payload (minimal version):

```json
{
  "name": "Lagos General Hospital",
  "domain": "lagosgeneral.com",
  "email": "info@lagosgeneral.com",
  "phone": "+2348099999999",
  "address": "12 Hospital Road, Lagos",
  "city": "Lagos",
  "country": 1,
  "facility_type": 1,
  "registration_number": "REG-1001",
  "subscription_plan": 1
}
```

If you want a slightly fuller example, you can also include:

```json
{
  "code": "LGH",
  "schema_name": "lagos_general",
  "state": 1,
  "lga": 1,
  "tax_id": "TAX-1001",
  "website": "https://lagosgeneral.com",
  "subscription_status": "trial",
  "billing_email": "billing@lagosgeneral.com",
  "bed_capacity": 150,
  "notes": "Primary teaching hospital"
}
```

You can also create the tenant and its root admin in one request by including a nested `root_admin` object in the tenant payload:

```json
{
  "name": "Lagos General Hospital",
  "domain": "lagosgeneral.com",
  "email": "info@lagosgeneral.com",
  "phone": "+2348099999999",
  "address": "12 Hospital Road, Lagos",
  "city": "Lagos",
  "country": 1,
  "facility_type": 1,
  "registration_number": "REG-1001",
  "subscription_plan": 1,
  "root_admin": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "rootadmin@lagosgeneral.com",
    "password": "StrongPass123!",
    "username": "john.doe",
    "phone": "+2348099999999",
    "employee_id": "LGH-ROOT-01"
  }
}
```

> Notes:
>
> - `country`, `facility_type`, and `subscription_plan` should match existing records in the database.
> - `code` and `schema_name` are often generated automatically if omitted.
> - For a first test, you can start with the minimal payload above.

4. If the tenant root admin was not created during tenant creation, create it now using the dedicated endpoint:

```http
POST /api/v1/tenants/tenants/{tenant_id}/create-root-admin/
```

Example root admin body:

```json
{
  "email": "rootadmin@lagosgeneral.com",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+2348099999999",
  "password": "StrongPass123!",
  "username": "john.doe",
  "employee_id": "LGH-ROOT-01"
}
```

5. Create the tenant admin using:

```http
POST /api/v1/tenants/tenants/{tenant_id}/create-admin/
```

Example body:

```json
{
  "email": "tenantadmin@lagosgeneral.com",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+2348099999999",
  "password": "StrongPass123!"
}
```

> `username` is optional. The backend will automatically generate a tenant-scoped `user_id` for the new tenant user (and a matching username if needed).

5. Login as the tenant admin:

Use only the tenant-scoped user ID and password for any tenant account (admin, doctor, nurse, receptionist, etc.):

```json
{
  "user_id": "LGH-ADM-1A2B3C",
  "password": "StrongPass123!"
}
```

Example success response:

```json
{
  "message": "Tenant admin login successful",
  "tenant": {
    "public_id": "13e656c8-72f7-445d-8238-b60f2cf3af67",
    "name": "Lagos General Hospital",
    "domain": "lagosgeneral.com"
  },
  "user": {
    "id": 2,
    "user_id": "LGH-ADM-1A2B3C",
    "username": "john.doe",
    "email": "tenantadmin@lagosgeneral.com",
    "role": "admin",
    "is_active": true
  },
  "tokens": {
    "access_token": "<jwt-access-token>",
    "refresh_token": "<jwt-refresh-token>"
  },
  "login_context": {
    "tenant_resolved_from": "user_id",
    "tenant_scoped_identifier_used": "LGH-ADM-1A2B3C"
  },
  "is_tenant_user": true
}
```

> `user_id` is the generated tenant-scoped login ID for the account. This applies to all users inside the tenant, not just the admin. The backend resolves the tenant automatically, so the payload should contain only these two fields.

6. Create doctors, nurses, pharmacists, receptionists, etc. with:

```http
POST /api/v1/tenants/users/
```

### Important login rule for all tenant users

Each tenant user account should use a unique tenant-scoped identifier:

- `employee_id` is the unique staff ID
- `username` can be omitted if you want the system to generate it automatically
- the login value can be either the generated `user_id` / `employee_id` or the username
- the backend will resolve the account inside the current tenant context

Example doctor payload:

```json
{
  "email": "dr.okafor@lagosgeneral.com",
  "first_name": "Ada",
  "last_name": "Okafor",
  "role": "doctor",
  "department": 1,
  "password": "DoctorPass123!"
}
```

If you want to provide a custom staff ID explicitly:

```json
{
  "email": "dr.okafor@lagosgeneral.com",
  "first_name": "Ada",
  "last_name": "Okafor",
  "role": "doctor",
  "department": 1,
  "password": "DoctorPass123!",
  "employee_id": "DOC-001"
}
```

7. Login for tenant staff can now use just two fields:

```json
{
  "user_id": "DOC-001",
  "password": "DoctorPass123!"
}
```

> `user_id` should be the tenant-scoped login value for the account (usually the generated `employee_id` / staff ID, or the username if you choose to use that instead). The backend resolves the tenant automatically, so you should not need extra tenant fields for this login call.

8. Create patients with a tenant-linked patient ID:

```http
POST /api/v1/patients/patients/
```

> This endpoint is for patient records and is different from tenant staff user creation. If the request is made by an authenticated tenant staff user, the backend will infer the tenant automatically and you do not need to send a `tenant` field. Only send `tenant` manually if you are calling the API outside the normal tenant-scoped staff session.

Example patient payload:

```json
{
  "first_name": "Grace",
  "last_name": "Adebayo",
  "date_of_birth": "1990-01-01",
  "gender": "female",
  "phone": "+2348012345678",
  "address": "10 Example Street",
  "city": "Lagos",
  "state": "Lagos",
  "country": "Nigeria",
  "password": "PatientPass123!"
}
```

Recommended required fields for a basic registration:

- `first_name`
- `last_name`
- `date_of_birth`
- `gender`
- `phone`
- `address`

Optional but commonly used fields:

- `email`
- `nin`
- `blood_group`
- `marital_status`
- `religion`
- `ethnicity`
- `occupation`
- `next_of_kin_name`
- `next_of_kin_phone`

### Patient login rule

Each patient gets:

- a unique `hospital_number` (auto-generated if you omit it)
- a unique `login_id` (defaults to the hospital number if not provided)
- a password you set during creation

Patients can log in with:

```json
{
  "identifier": "PAT-2026-000001",
  "password": "PatientPass123!"
}
```

Or use the patient endpoint ID / hospital number if needed.

9. Patient login endpoint:

```http
POST /api/v1/patients/login/
```

## 4) Communication Profile API

The **Communication Profile** gives each tenant its own sender identity for email and SMS, so outbound messages use the hospital's own verified "from" address/number and its logo/name in branded email templates. A profile is created automatically whenever a tenant is created.

Base URL: `http://localhost:8000/api/v1/tenants/communication-profile/`

All requests require a valid access token: `Authorization: Bearer <access_token>`.

### GET /current/ — Get the current tenant's profile

Returns the communication profile for the authenticated user's own tenant. If none exists, one is created automatically.

```http
GET /api/v1/tenants/communication-profile/current/
```

Example response (200 OK):

```json
{
  "id": 1,
  "tenant": 1,
  "tenant_name": "Lagos General Hospital",
  "tenant_code": "LGH",
  "is_active": true,
  "email_from": "",
  "from_name": "",
  "reply_to": "",
  "verified_domain": "",
  "email_provider": "",
  "email_username": "",
  "email_password": "",
  "email_host": "",
  "email_port": null,
  "email_use_tls": true,
  "sms_provider": "",
  "sms_sender_id": "",
  "sms_phone_number": "",
  "sms_api_key": "",
  "sms_country_code": "NG",
  "consent_tracking_enabled": true,
  "opt_out_message": "Reply STOP to unsubscribe",
  "dnd_enabled": false,
  "message_templates": {},
  "email_enabled": true,
  "sms_enabled": true,
  "daily_email_limit": 1000,
  "daily_sms_limit": 500,
  "created_at": "2024-01-01T10:00:00.000000Z",
  "updated_at": "2024-01-01T10:00:00.000000Z"
}
```

### PATCH /current/ — Update the current tenant's profile

Use `PATCH` (or `PUT`) to update the current tenant's communication settings. Only send the fields you want to change.

```http
PATCH /api/v1/tenants/communication-profile/current/
```

Example payload:

```json
{
  "email_from": "no-reply@lagosgeneral.com",
  "from_name": "Lagos General Hospital",
  "reply_to": "support@lagosgeneral.com",
  "verified_domain": "mail.lagosgeneral.com",
  "email_provider": "sendgrid",
  "email_host": "smtp.sendgrid.net",
  "email_port": 587,
  "email_username": "apikey",
  "email_password": "SG.super-secret-sendgrid-key",
  "email_use_tls": true,
  "sms_provider": "twilio",
  "sms_sender_id": "LagosGH",
  "sms_phone_number": "+2348099999999",
  "sms_api_key": "AC-super-secret-twilio-key",
  "sms_country_code": "NG",
  "daily_email_limit": 2000,
  "daily_sms_limit": 1000
}
```

> `email_password` and `sms_api_key` are encrypted at rest. The API returns the plaintext value in the response for convenience, so you can echo back the same value on update without it being re-encrypted.

### CRUD endpoints (system admin or tenant-scoped)

The router also exposes standard list/retrieve/create/update/delete under the same base URL:

- `GET  /api/v1/tenants/communication-profile/` — list profiles (system admin sees all; tenant users see only their own)
- `POST /api/v1/tenants/communication-profile/` — create a profile (tenant is auto-resolved from the request)
- `GET  /api/v1/tenants/communication-profile/{id}/` — retrieve a specific profile
- `PUT/PATCH /api/v1/tenants/communication-profile/{id}/` — update a profile
- `DELETE /api/v1/tenants/communication-profile/{id}/` — delete a profile

Example create payload (same shape as the `PATCH /current/` example above; `tenant` is resolved automatically):

```json
{
  "email_from": "no-reply@lagosgeneral.com",
  "from_name": "Lagos General Hospital",
  "sms_sender_id": "LagosGH",
  "sms_phone_number": "+2348099999999",
  "opt_out_message": "Reply STOP to opt out",
  "message_templates": {
    "email": {
      "appointment_reminder": "Dear {{ patient_name }}, your appointment is on {{ date }}."
    },
    "sms": {
      "password_reset": "Your password reset token is {{ token }}."
    }
  }
}
```

### Field reference

| Field | Type | Purpose |
|-------|------|---------|
| `email_from` | string | Verified sender email (e.g. `no-reply@hospital.org`) |
| `from_name` | string | Display name shown in the client's inbox |
| `reply_to` | string | Address where replies should be delivered |
| `verified_domain` | string | Verified sending domain/subdomain |
| `email_provider` | string | `sendgrid` / `ses` / `smtp` / `default` |
| `email_host` / `email_port` / `email_username` / `email_password` / `email_use_tls` | — | SMTP connection settings |
| `sms_provider` | string | `twilio` / `messagebird` / `vonage` / `default` |
| `sms_sender_id` | string | Alphanumeric sender ID or number |
| `sms_phone_number` | string | Dedicated SMS number |
| `sms_api_key` | string | Encrypted provider key |
| `sms_country_code` | string | Region code (default `NG`) |
| `consent_tracking_enabled` | boolean | Track patient opt-in/opt-out |
| `opt_out_message` | string | STOP/unsubscribe wording |
| `dnd_enabled` | boolean | Do Not Disturb enabled |
| `message_templates` | object | Pre-approved templates per channel (`email`/`sms`) and type |
| `email_enabled` / `sms_enabled` | boolean | Channel on/off |
| `daily_email_limit` / `daily_sms_limit` | integer | Daily send caps |

## 5) Quick check

If you want to confirm the public tenant exists:

```bash
python manage.py shell
>>> from tenants.models import Tenant
>>> Tenant.objects.filter(schema_name='public').exists()
```
https://docs.google.com/spreadsheets/d/136c9OGjTuJ_Nd_EjAUtfyH7m5EXjVIvl/edit?gid=1573445100#gid=1573445100


YrNWswCs3h5D

NET-DOC-30E357