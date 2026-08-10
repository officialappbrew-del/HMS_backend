from django.contrib import admin


# Super Admin platform endpoints are housed in the API layer (superadmin/views.py).
# The Django admin still exposes the underlying platform models (Tenant, users.GlobalUser,
# core.SystemSetting, core.AuditLog) via their own admin registrations. No additional
# admin registrations are required here.
