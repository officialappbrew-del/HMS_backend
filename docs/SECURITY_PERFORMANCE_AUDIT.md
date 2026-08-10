# SmartCare HMS — Security & Performance Audit Report

**Date:** Re-verified against current codebase
**Scope:** Query-time review of settings, authentication, middleware, models, views, serializers, tenant isolation, integration endpoints, and deployment config (Dockerfile, docker-compose, render.yaml).

---

## Executive Summary

This report lists the **open (unresolved)** security and performance issues found during a
systematic review of the SmartCare HMS backend. Each issue was verified against the current
source code.

| Priority | Open Issues |
|----------|-------------|
| 🔴 Critical Security | 6 |
| 🟡 High Security | 6 |
| 🔴 Critical Performance | 7 |
| 🟡 Medium Performance | 6 |

---

## 🔴 Critical Security Issues

### 1. Weak Default Encryption Key
- **File:** `smartcare_hms/settings.py`
- **Issue:** `ENCRYPTION_KEY` still has a hardcoded fallback
  `'your-32-char-key-for-encryption-change-this'`. A runtime warning is emitted when the key is
  insecure, but the app still boots with a trivially reversible key.
- **Risk:** Encrypted fields (2FA secrets, backup codes, RSA private keys) are reversible if the
  key is not overridden in production.
- **Fix:** Set a strong (>32 char, random) `ENCRYPTION_KEY` in all production environments; fail
  fast on insecure defaults.

### 2. Rate Limiting Not Fully Effective
- **File:** `smartcare_hms/settings.py`
- **Issue:** DRF `DEFAULT_THROTTLE_CLASSES` are enabled, **but**:
  - The global `RateLimitMiddleware` is still **commented out**.
  - The cache backend is `LocMemCache`, so throttle counters are **per-process** and not shared
    across Gunicorn workers.
- **Risk:** Brute-force login, credential stuffing, and API abuse are not reliably blocked under a
  multi-worker deployment.
- **Fix:** Enable the middleware and move throttling to a shared Redis backend.

### 3. 2FA Not Enforced for Tenant Users
- **File:** `users/authentication.py`
- **Issue:** The 2FA check
  (`if getattr(user, 'two_fa_enabled') and not payload.get('two_fa_verified')`) executes **only in
  the global-user path**. The tenant-user path returns before this check, so tenant accounts are
  **not** subject to 2FA enforcement.
- **Risk:** Compromised tenant-user credentials can access the system without a second factor.
- **Fix:** Apply the 2FA check to the tenant-user path as well.

### 4. Integration Tenant Resolution Bug (HL7)
- **File:** `integration/views.py`
- **Issue:** `HL7IntegrationAPIView` resolves tenant via `request.user.tenant_user`, but
  `IntegrationAPIKeyAuthentication` sets `request.integration_client` (not `request.user`). On
  key-authenticated requests the tenant may be `None`, so HL7 messages may not be scoped to the
  correct tenant.
- **Risk:** Cross-tenant data writes / incorrect tenant attribution for lab results.
- **Fix:** Use `request.integration_client.tenant` in HL7 handling.

### 5. Password Change Does Not Invalidate Existing Tokens
- **File:** `users/serializers.py` / `users/views.py`
- **Issue:** No token/session invalidation is performed on password change.
- **Risk:** A stolen session or JWT remains valid for its full lifetime after a password reset.
- **Fix:** Rotate/invalidate outstanding refresh tokens and sessions on password change.

### 6. CSRF Cookie Still Not HttpOnly by Default
- **File:** `smartcare_hms/settings.py`
- **Issue:** `CSRF_COOKIE_HTTPONLY = config('CSRF_COOKIE_HTTPONLY', default=False)` still defaults
  to `False`. (`CSRF_COOKIE_SAMESITE` now defaults to `Lax` — improved, but HttpOnly remains open.)
- **Risk:** If any XSS exists, the CSRF cookie is readable by script.
- **Fix:** Set `CSRF_COOKIE_HTTPONLY=True` if the frontend never reads the cookie from JS; enforce
  `SameSite=Lax`/`Strict` in production.

---

## 🟡 High Security Issues

### 7. No Brute-Force Lockout for Global Users
- **Issue:** Global users rely on DRF throttling and session auth for admin, but the coarse IP
  `RateLimitMiddleware` is disabled and there is no admin-path brute-force lockout.
- **Fix:** Enable the middleware; add per-IP and per-account lockout on `/admin/`.

### 8. Per-Tenant Credentials Encrypted With a Single Global Key
- **File:** `tenants/security.py`
- **Issue:** All tenants share one `ENCRYPTION_KEY`. A key breach decrypts credentials for every
  tenant.
- **Fix:** Use per-tenant key derivation or an HSM/KMS.

### 9. Static Fernet Key in `EncryptedField`
- **File:** `core/models.py`
- **Issue:** `EncryptedField.get_fernet()` caches a single Fernet key per process. Rotating the key
  makes prior data unreadable; there is no versioned-key scheme.
- **Fix:** Add key versioning and a re-encryption migration path.

### 10. Allowed Hosts Includes Production Domains by Default
- **File:** `smartcare_hms/settings.py`
- **Issue:** Render domains are in the default `ALLOWED_HOSTS`.
- **Fix:** Tighten `ALLOWED_HOSTS` per environment.

### 11. Elasticsearch Runs With Security Disabled
- **File:** `docker-compose.yml`
- **Issue:** `xpack.security.enabled=false` exposes ES (port 9200) with no authentication.
- **Fix:** Enable ES security or restrict port 9200 to an internal network.

### 12. No Upload Size Limits on Some Media Endpoints
- **Issue:** Profile/logo/patient-document uploads rely only on global
  `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE`.
- **Fix:** Add per-endpoint size limits and file-type allowlists (magic-byte validation).

---

## 🔴 Critical Performance Issues

### 13. No Redis Cache (LocMemCache)
- **File:** `smartcare_hms/settings.py`
- **Issue:** Cache backend is `LocMemCache`. In multi-process deployments each worker owns its own
  cache, so throttle counters, sessions, and caches are not shared across workers.
- **Fix:** Enable Redis via `django_redis` for cache + sessions + throttle buckets.

### 14. Database Session Engine
- **File:** `smartcare_hms/settings.py`
- **Issue:** `SESSION_ENGINE = 'django.contrib.sessions.backends.db'` adds a DB round-trip per
  request.
- **Fix:** Move sessions to Redis/cache when Redis is enabled.

### 15. No Connection Pooling
- **Issue:** No PgBouncer equivalent; each worker holds its own PostgreSQL connection.
- **Fix:** Add PgBouncer or set a sensible `CONN_MAX_AGE`.

### 16. N+1 Queries in Audit Logging
- **File:** `patients/views.py`
- **Issue:** `_serialize_for_audit` full-serializes a patient (with related lookups) on every write
  path.
- **Fix:** Serialize only needed fields; batch audit writes (see #19).

### 17. Inline Blocking Email Sending
- **File:** `patients/views.py`
- **Issue:** `_dispatch_appointment_reminder` calls `send_mail` synchronously inside the request
  path.
- **Fix:** Route through Celery (`.delay()`).

### 18. Row-by-Row Bulk Patient Upload
- **File:** `patients/views.py`
- **Issue:** `_process_bulk_upload` does individual `Patient.objects.create` per row and loads the
  whole CSV into memory via `list(reader)`.
- **Fix:** Use `bulk_create` in chunks; stream CSV rows; wrap in a single transaction.

### 19. Thread-per-Request Async Audit
- **File:** `patients/views.py`
- **Issue:** Uses `threading.Thread` for audit writes instead of Celery.
- **Fix:** Move audit writes to Celery for reliability and backpressure.

---

## 🟡 Medium Performance Issues

### 20. Missing `select_related`/`prefetch_related` on Nested Endpoints
- **File:** `patients/views.py` (`visits`, `documents`, `allergies`, `medications`,
  `appointments`) and analogous endpoints in `clinical`/`lab`/`pharmacy`.
- **Issue:** `get_queryset` only does `select_related('tenant')` on patients.
- **Fix:** Add `select_related`/`prefetch_related` on nested endpoints.

### 21. Missing Indexes on Frequently Searched Patient Columns
- **Columns:** `phone`, `email`, `nin`, `hospital_number`, `mrn`, `login_id`.
- **Issue:** `icontains` searches need `pg_trgm` GIN indexes to be effective.
- **Fix:** Add composite + `pg_trgm` GIN indexes.

### 22. Template Re-render Per Password-Reset Email
- **Issue:** Templates are re-rendered for every password-reset email.
- **Fix:** Cache compiled templates.

### 23. Schema-Switch Cost of Global Employee-ID Uniqueness Check
- **Issue:** The global employee-ID uniqueness check iterates every active tenant schema.
- **Fix:** Maintain a global lookup table/index for employee IDs.

### 24. Elasticsearch Heap Left at 512 MB
- **File:** `docker-compose.yml`
- **Issue:** `ES_JAVA_OPTS=-Xms512m -Xmx512m` is minimal for production.
- **Fix:** Raise ES heap or scale ES nodes.

### 25. Integration Client Authentication Iterates All Active Clients
- **File:** `integration/views.py`
- **Issue:** `IntegrationAPIKeyAuthentication` loops `IntegrationClient.objects.filter(is_active=True)`
  client-by-client instead of a direct prefix lookup.
- **Fix:** Add a prefix-indexed lookup (e.g., query by first N chars of prefix).

---

## Recommended Remediation Plan

### Step 1 — Critical Security (do first)
1. Set strong, unique `ENCRYPTION_KEY` and `JWT_SIGNING_KEY` in all production envs; fail fast on
   insecure defaults.
2. Enable the global `RateLimitMiddleware` with a shared Redis-backed throttle.
3. Enforce 2FA on the tenant-user path too.
4. Fix `HL7IntegrationAPIView` tenant resolution to use `request.integration_client.tenant`.
5. Rotate/invalidate tokens on password change.
6. Set `CSRF_COOKIE_HTTPONLY=True` and confirm `SameSite=Lax`/`Strict` in prod.

### Step 2 — Performance (high impact)
1. Enable Redis for cache, sessions, and throttle buckets.
2. Add composite/pg_trgm GIN indexes on high-traffic patient search columns.
3. Batch-bulk patient creation (`bulk_create`) and stream CSV.
4. Add `select_related`/`prefetch_related` on nested endpoints.
5. Route email and audit writes through Celery.
6. Add PgBouncer or `CONN_MAX_AGE`.

### Step 3 — Operational Hardening
1. Enable Elasticsearch security and restrict port 9200.
2. Raise Elasticsearch heap or scale ES nodes.
3. Tighten `ALLOWED_HOSTS` per environment.
4. Add per-endpoint upload limits and file-type allowlists.
5. Add a prefix-indexed lookup for integration clients.

---

*This file lists the open (unresolved) security & performance issues of the SmartCare HMS codebase.*
