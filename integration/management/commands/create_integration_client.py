from django.core.management.base import BaseCommand, CommandError

from integration.models import IntegrationClient
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Create an integration client and print a generated API key for HL7/FHIR access.'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Unique client name, e.g. lab-system')
        parser.add_argument('--description', default='', help='Human-readable description for the client')
        parser.add_argument('--tenant-id', type=int, default=None, help='Optional tenant ID to attach the client to')
        parser.add_argument('--prefix', default='hms_', help='API key prefix')

    def handle(self, *args, **options):
        name = options['name']
        tenant = None
        tenant_id = options.get('tenant_id')
        if tenant_id is not None:
            try:
                tenant = Tenant.objects.get(id=tenant_id)
            except Tenant.DoesNotExist:
                raise CommandError(f'Tenant with id {tenant_id} does not exist.')

        if IntegrationClient.objects.filter(name=name).exists():
            raise CommandError(f'Integration client {name} already exists.')

        client, raw_key = IntegrationClient.generate_api_key(
            name=name,
            tenant=tenant,
            description=options['description'],
            prefix=options['prefix'],
        )

        self.stdout.write(self.style.SUCCESS(f'Created integration client: {client.name}'))
        self.stdout.write(self.style.WARNING('Use this API key once in a secure place:'))
        self.stdout.write(self.style.HTTP_INFO(raw_key))
        self.stdout.write(self.style.WARNING('Authorization header format: Bearer ' + raw_key))
