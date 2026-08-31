#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcare_hms.settings')
django.setup()

from django.db import connection
connection.set_schema_to_public()

from tenants.models import Tenant, TenantDomain, SubscriptionPlan
from core.models import FacilityType, Country

# Get or create a default Country
country, _ = Country.objects.get_or_create(
    name='Nigeria',
    defaults={'code': 'NG'}
)

# Get or create a default FacilityType
facility_type, _ = FacilityType.objects.get_or_create(
    name='General Hospital',
    defaults={'description': 'General Hospital'}
)

# Get or create a default SubscriptionPlan
subscription_plan, _ = SubscriptionPlan.objects.get_or_create(
    name='Platform Plan',
    defaults={
        'description': 'Platform subscription plan',
        'price_monthly': 0,
        'price_quarterly': 0,
        'price_yearly': 0,
        'is_active': True,
    }
)

# Create the public schema tenant if it doesn't exist
public_tenant, created = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={
        'name': 'SmartCare Platform',
        'is_active': True,
        'facility_type': facility_type,
        'subscription_plan': subscription_plan,
        'country': country,
    }
)

if created:
    print(f"✅ Created public schema tenant: {public_tenant.name}")
else:
    print(f"✅ Public schema tenant already exists: {public_tenant.name}")

# Now add domain entries for localhost and 127.0.0.1
for domain_name in ['localhost', '127.0.0.1']:
    if not TenantDomain.objects.filter(domain=domain_name).exists():
        domain = TenantDomain.objects.create(
            domain=domain_name,
            tenant=public_tenant,
            is_primary=(domain_name == 'localhost')
        )
        print(f"✅ Created domain entry: {domain_name} -> {public_tenant.name}")
    else:
        existing = TenantDomain.objects.get(domain=domain_name)
        print(f"✅ Domain entry for {domain_name} already exists")

print("\n✅ Localhost domain setup complete!")
