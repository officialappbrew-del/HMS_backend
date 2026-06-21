from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings

from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Create database schema for a tenant'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_id', type=int, help='ID of the tenant')
    
    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            self.stderr.write(f'Tenant with ID {tenant_id} does not exist')
            return
        
        # Create schema
        schema_name = tenant.schema_name
        
        with connection.cursor() as cursor:
            # Check if schema exists
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", [schema_name])
            if cursor.fetchone():
                self.stdout.write(f'Schema {schema_name} already exists')
                return
            
            # Create schema
            cursor.execute(f'CREATE SCHEMA {schema_name}')
            self.stdout.write(f'Created schema {schema_name}')
            
            # Set search path and create tables
            cursor.execute(f'SET search_path TO {schema_name}')
            
            # Create tables for tenant apps
            from django.core.management import call_command
            call_command('migrate', database='default', schema_name=schema_name, interactive=False)
            
            # Reset search path
            cursor.execute('SET search_path TO public')
        
        self.stdout.write(f'Successfully created schema and tables for tenant {tenant.name}')