# SmartCare HMS quick setup

Use this file as the only setup guide.

## 1) Install and run

```bash
cd C:\Users\Ekene-onwon\Desktop\Codes\HosPManagement\HMS_backend
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
- Tenant users: http://localhost:8000/api/v1/tenants/users/
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

> Notes:
> - `country`, `facility_type`, and `subscription_plan` should match existing records in the database.
> - `code` and `schema_name` are often generated automatically if omitted.
> - For a first test, you can start with the minimal payload above.

4. Create the tenant admin using:

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

## 4) Quick check

If you want to confirm the public tenant exists:

```bash
python manage.py shell
>>> from tenants.models import Tenant
>>> Tenant.objects.filter(schema_name='public').exists()
```

