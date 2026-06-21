from django.conf import settings
from django.db import connections
from django.db.utils import ConnectionDoesNotExist


class TenantDatabaseRouter:
    """
    Database router for multi-tenant architecture.
    Routes queries to appropriate tenant schemas.
    """
    
    def __init__(self):
        self.tenant_models = {
            'tenants.TenantUser',
            'tenants.Department',
            'tenants.TenantSetting',
            'tenants.TenantModule',
            'tenants.TenantInvitation',
            'tenants.TenantActivityLog',
            'tenants.TenantBackup',
            # Add other tenant-specific models here
        }
        self.global_models = {
            'tenants.Tenant',
            'tenants.SubscriptionPlan',
            'users.GlobalUser',
            'users.User2FA',
            'users.RSAKey',
            'users.UserSession',
            'users.SecurityEvent',
            'users.UserNotification',
            'core.Country',
            'core.State',
            'core.LGA',
            'core.FacilityType',
            'core.Specialization',
            'core.Language',
            'core.NotificationTemplate',
            'core.SystemSetting',
            'core.AuditLog',
            'core.BackupLog',
        }
    
    def db_for_read(self, model, **hints):
        """Suggest database for read operations."""
        model_name = f"{model._meta.app_label}.{model._meta.model_name}"
        
        if model_name in self.global_models:
            return 'default'
        elif model_name in self.tenant_models:
            return 'default'  # Same database, different schema
        return None
    
    def db_for_write(self, model, **hints):
        """Suggest database for write operations."""
        model_name = f"{model._meta.app_label}.{model._meta.model_name}"
        
        if model_name in self.global_models:
            return 'default'
        elif model_name in self.tenant_models:
            return 'default'  # Same database, different schema
        return None
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects."""
        # Allow relations within same database
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Determine if migration should be applied to database."""
        full_model_name = f"{app_label}.{model_name}" if model_name else None
        
        if full_model_name in self.global_models:
            # Global models go to public schema
            return db == 'default' and hints.get('schema_name', 'public') == 'public'
        elif full_model_name in self.tenant_models:
            # Tenant models go to tenant schemas
            return db == 'default' and hints.get('schema_name') != 'public'
        
        return None