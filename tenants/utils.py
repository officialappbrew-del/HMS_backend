from django.db import connection
from django.conf import settings
from django.core.exceptions import PermissionDenied

from .models import Tenant


def get_current_tenant():
    """Get current tenant from thread local."""
    from django.db import connection
    return getattr(connection, 'tenant', None)


def set_current_tenant(tenant):
    """Set current tenant in thread local."""
    from django.db import connection
    connection.tenant = tenant
    
    # Set schema for connection
    if tenant:
        connection.set_schema(tenant.schema_name)
    else:
        connection.set_schema('public')


def tenant_context(tenant):
    """Context manager for tenant operations."""
    class TenantContext:
        def __init__(self, tenant):
            self.tenant = tenant
            self.old_tenant = get_current_tenant()
        
        def __enter__(self):
            set_current_tenant(self.tenant)
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            set_current_tenant(self.old_tenant)
    
    return TenantContext(tenant)


def require_tenant_admin(func):
    """Decorator to require tenant admin access."""
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        # Check if user is a tenant user
        if not hasattr(user, 'tenant_user') or not user.tenant_user:
            raise PermissionDenied("Not a tenant user")
        
        # Check if user is admin
        if user.tenant_user.role != 'admin':
            raise PermissionDenied("Tenant admin access required")
        
        return func(request, *args, **kwargs)
    
    return wrapper


def get_tenant_from_request(request):
    """Get tenant from request object."""
    # Check if tenant is already set in request
    if hasattr(request, 'tenant'):
        return request.tenant
    
    # Check if user is a tenant user
    if hasattr(request.user, 'tenant_user') and request.user.tenant_user:
        return request.user.tenant_user.tenant
    
    # Try to get from domain
    host = request.get_host().split(':')[0]
    try:
        return Tenant.objects.get(domain=host, is_active=True)
    except Tenant.DoesNotExist:
        return None


def create_tenant_schema(tenant):
    """Create database schema for a new tenant."""
    schema_name = tenant.schema_name
    
    with connection.cursor() as cursor:
        # Create schema
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS {schema_name}')
        
        # Set search path
        cursor.execute(f'SET search_path TO {schema_name}')
        
        # Create tables for tenant apps
        # This would be done via migrations in production
        # For now, we'll create essential tables
        
        # Create tenant users table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants_tenantuser (
                id BIGSERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenants_tenant(id),
                username VARCHAR(150) NOT NULL,
                email VARCHAR(254) NOT NULL,
                password VARCHAR(128) NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                -- ... other fields
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT true,
                UNIQUE(tenant_id, username),
                UNIQUE(tenant_id, email)
            )
        ''')
        
        # Reset search path
        cursor.execute('SET search_path TO public')
    
    return schema_name


def list_tenant_schemas():
    """List all tenant schemas in the database."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT LIKE 'pg_%' 
            AND schema_name != 'information_schema' 
            AND schema_name != 'public'
        """)
        return [row[0] for row in cursor.fetchall()]