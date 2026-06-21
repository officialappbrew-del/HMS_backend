from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings

from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Delete database schema for a tenant'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_id', type=int, help='ID of the tenant')
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation'
        )
    
    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        force = options['force']
        
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            self.stderr.write(f'Tenant with ID {tenant_id} does not exist')
            return
        
        schema_name = tenant.schema_name
        
        if not force:
            confirm = input(f'Are you sure you want to delete schema {schema_name}? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write('Operation cancelled')
                return
        
        with connection.cursor() as cursor:
            # Drop schema
            cursor.execute(f'DROP SCHEMA IF EXISTS {schema_name} CASCADE')
            self.stdout.write(f'Dropped schema {schema_name}')
        
        self.stdout.write(f'Successfully deleted schema for tenant {tenant.name}')