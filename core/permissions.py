from rest_framework import permissions


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


class IsDoctor(permissions.BasePermission):
    """Check if user is a doctor."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'doctor'


class IsNurse(permissions.BasePermission):
    """Check if user is a nurse."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'nurse'


class IsPharmacist(permissions.BasePermission):
    """Check if user is a pharmacist."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'pharmacist'


class IsLabTechnician(permissions.BasePermission):
    """Check if user is a lab technician."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'lab_technician'


class IsReceptionist(permissions.BasePermission):
    """Check if user is a receptionist."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'receptionist'


class IsPatient(permissions.BasePermission):
    """Check if user is a patient."""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'patient'


class HasPermission(permissions.BasePermission):
    """Check if user has specific permission."""
    
    def __init__(self, permission_codename):
        self.permission_codename = permission_codename
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_perm(self.permission_codename)