from rest_framework import permissions


def _get_user_role(user):
    if user is None:
        return None

    tenant_user = getattr(user, 'tenant_user', None)
    if tenant_user is not None:
        return getattr(tenant_user, 'role', None)

    return getattr(user, 'role', None)


class IsSystemAdmin(permissions.BasePermission):
    """Check if user is a system administrator."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.role == 'system_admin'
        )


class IsTenantAdmin(permissions.BasePermission):
    """Check if user is a tenant administrator."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.role == 'tenant_admin' or
            request.user.is_staff
        )


class IsTenantRootAdminOrGlobalAdmin(permissions.BasePermission):
    """Check if user is a tenant root admin or global admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'is_superuser', False):
            return True

        if getattr(request.user, 'role', None) in ['super_admin', 'system_admin']:
            return True

        tenant_user = getattr(request.user, 'tenant_user', None)
        return bool(tenant_user and getattr(tenant_user, 'is_root_admin', False))


class IsDoctor(permissions.BasePermission):
    """Check if user is a doctor."""
    
    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(request.user.is_authenticated and role == 'doctor')


class IsNurse(permissions.BasePermission):
    """Check if user is a nurse."""
    
    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(request.user.is_authenticated and role == 'nurse')


class IsPharmacist(permissions.BasePermission):
    """Check if user is a pharmacist."""
    
    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(request.user.is_authenticated and role == 'pharmacist')


class IsPharmacistOrTenantAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'pharmacist' or
            request.user.role == 'tenant_admin' or
            request.user.is_staff or
            request.user.is_superuser
        )


class IsDoctorOrPharmacist(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'doctor' or request.user.role == 'pharmacist'
        )


class IsDoctorOrNurse(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'doctor' or request.user.role == 'nurse'
        )


class IsLabTechnician(permissions.BasePermission):
    """Check if user is a lab technician."""
    
    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(request.user.is_authenticated and role == 'lab_tech')


class IsReceptionist(permissions.BasePermission):
    """Check if user is a receptionist."""
    
    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(request.user.is_authenticated and role == 'receptionist')


class IsFinanceStaff(permissions.BasePermission):
    """Allow access to financial and billing operations only for finance roles or admins."""

    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(
            request.user.is_authenticated and role in {
                'admin', 'tenant_admin', 'accountant', 'billing_officer', 'super_admin', 'system_admin'
            }
        )


class IsClinicalStaff(permissions.BasePermission):
    """Allow clinical workflows for staff who can manage care, but not receptionists."""

    def has_permission(self, request, view):
        role = _get_user_role(getattr(request, 'user', None))
        return bool(
            request.user.is_authenticated and role in {
                'doctor', 'nurse', 'pharmacist', 'lab_tech', 'admin', 'tenant_admin', 'super_admin', 'system_admin'
            }
        )


class IsPatient(permissions.BasePermission):
    """Check if user is a patient."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'patient'


class IsAuditViewer(permissions.BasePermission):
    """Allow viewing audit logs based on access level.

    Granted to:
      - superusers and global system/support/auditor roles
      - tenant administrators (role ``admin``) and tenant root admins
    Lower-privilege tenant roles (doctor, nurse, pharmacist, …) are denied.
    """

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return False

        if getattr(user, 'is_superuser', False):
            return True

        role = getattr(user, 'role', None)
        if role in ('system_admin', 'super_admin', 'auditor', 'support'):
            return True

        if (
            role == 'admin'
            or getattr(user, 'is_root_admin', False)
            or getattr(user, 'is_global_admin', False)
        ):
            return True

        return False


class HasPermission(permissions.BasePermission):
    """Check if user has specific permission."""
    
    def __init__(self, permission_codename):
        self.permission_codename = permission_codename
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_perm(self.permission_codename)