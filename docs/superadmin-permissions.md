# Super Admin Permissions

## Overview

The Super Admin module enforces role-based access control (RBAC) for platform-wide actions. There are two layers:

1. **Backend enforcement** via DRF permission classes
2. **Frontend gating** via React hooks and localStorage flags

---

## Seniority Hierarchy

| Role | Level | Notes |
|------|-------|-------|
| `super_admin` | 3 | Most senior. Can manage all other admins. |
| `system_admin` | 2 | Can manage `support` and `auditor` admins only. |
| `support` | 1 | Cannot manage other admins. |
| `auditor` | 1 | Cannot manage other admins. |
| Django `is_superuser` | 4 | Bypasses all checks. |

---

## Backend Implementation

### Permission Classes

**`core/permissions.py`**

- `HasTenantPermission(flag)`
  - Checks a boolean field on `GlobalUser`: `can_create_tenants`, `can_suspend_tenants`, `can_delete_tenants`, `can_view_all_tenants`, `can_manage_admin_permissions`
  - Django superusers bypass the check.

- `IsSeniorAdmin`
  - Validates the requester's role is in the hierarchy.
  - Provides `can_manage(actor, target)` to block actions on admins of equal or higher seniority.

### Enforced Endpoints

| Endpoint | Permission | Effect |
|----------|-----------|--------|
| `GET /api/v1/superadmin/tenants/` | `HasTenantPermission('can_view_all_tenants')` | Only admins with the flag can list tenants. |
| `POST /api/v1/superadmin/tenants/create/` | `HasTenantPermission('can_create_tenants')` | Only admins with the flag can create tenants. |
| `GET /api/v1/superadmin/tenants/<id>/` | `HasTenantPermission('can_suspend_tenants')` | Only admins with the flag can view tenant details. |
| `POST /api/v1/superadmin/tenants/<id>/toggle/` | `HasTenantPermission('can_suspend_tenants')` | Only admins with the flag can activate/suspend tenants. |
| `GET /api/v1/superadmin/admins/` | `IsSeniorAdmin` | Filters out admins above the requester's level. |
| `POST /api/v1/superadmin/admins/` | `IsSeniorAdmin` + `can_create_tenants` or superuser | Only senior admins with the tenant-create flag can create other admins. |
| `PUT /api/v1/superadmin/admins/<id>/` | `IsSeniorAdmin` + `can_manage()` | Blocks editing admins of equal or higher seniority. If the request changes any permission field, the requester must also have `can_manage_admin_permissions` or be a superuser. |
| `GET /api/v1/superadmin/admins/<id>/` | `IsSeniorAdmin` + `can_manage()` | Blocks viewing admins of equal or higher seniority. |
| `DELETE /api/v1/superadmin/admins/<id>/` | `IsSeniorAdmin` + `can_manage()` | Blocks deleting admins of equal or higher seniority. |

### Superuser Defaults

`createsuperuser` sets all five permission flags to `True` and assigns the `super_admin` role, ensuring the initial admin has full access.

---

## Frontend Implementation

### Auth State

`src/pages/SuperAdmin/AdminLogin.jsx` persists the following to `localStorage` on login:
- `userRole`
- `userIsRootAdmin`
- `userIsSuperuser`
- `canCreateTenants`
- `canSuspendTenants`
- `canDeleteTenants`
- `canViewAllTenants`
- `canManageAdminPermissions`

### Permission Hook

**`src/hooks/useAdminPermissions.js`**

- `useAdminPermissions()` — returns the five permission booleans and refreshes on `authChanged` events.
- `isSuperUser()` — returns `true` if role is `super_admin`, `userIsRootAdmin` is true, or `userIsSuperuser` is true.

### Gated UI

**Tenant Management** (`TenantManagement.jsx`)
- **New Tenant** button: hidden unless `canCreateTenants` or `isSuperUser()`
- **View / Edit / Activate / Deactivate** buttons: disabled unless the corresponding permission or `isSuperUser()`

**Global Admins** (`GlobalAdmins.jsx`)
- **My Profile** button: allows any logged-in admin to view and update their own first name, last name, email, phone, and password
- **New Admin** button: hidden unless `canCreateTenants` or `isSuperUser()`
- Admin list: filters out admins above the current user's role level
- Role labels: superusers show as `Super Admin`, others show their role display name
- **Edit / Delete** buttons: hidden for admins the current user cannot manage, and also hidden for the superadmin record unless the current user is the superuser
- **Manage Admin Permissions** checkbox: only visible in create/edit modals when `canManageAdminPermissions` or `isSuperUser()` is true

---

## Notes

- Frontend gating is for UX only. All authorization must be enforced backend.
- `IsSeniorAdmin.can_manage()` prevents self-targeted edits/deletes.
- The `GlobalAdminSerializer` now exposes `is_superuser` so the frontend can detect Django superusers.
