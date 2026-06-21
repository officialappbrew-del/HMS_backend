# tenants_setup.py
# Run inside Django shell:
# python manage.py shell < tenants_setup.py

from django.utils import timezone

from tenants.models import Tenant, TenantDomain, SubscriptionPlan
from core.models import Country, State, LGA, FacilityType

# Create or fetch the base country
country, country_created = Country.objects.get_or_create(
    code='NG',
    defaults={
        'name': 'Nigeria',
        'phone_code': '+234',
        'currency': 'NGN',
        'timezone': 'Africa/Lagos',
    },
)

# Create or fetch a default state and LGA
state, state_created = State.objects.get_or_create(
    code='LAG',
    defaults={
        'name': 'Lagos',
        'country': country,
    },
)

lga, lga_created = LGA.objects.get_or_create(
    name='Ikeja',
    defaults={'state': state},
)

# Create or fetch a default facility type with required code field
facility_type, facility_type_created = FacilityType.objects.get_or_create(
    code='HOSP',
    defaults={
        'name': 'Hospital',
        'description': 'General healthcare facility',
    },
)

# Create or fetch a default subscription plan
subscription_plan, plan_created = SubscriptionPlan.objects.get_or_create(
    code='PUBLIC_FREE',
    defaults={
        'name': '1Public Free Plan',
        'description': 'Free plan for the public/system tenant',
        'price_monthly': 0,
        'price_quarterly': 0,
        'price_yearly': 0,
        'currency': 'NGN',
        'max_users': 10,
        'max_patients': 100,
        'max_storage_gb': 1,
        'max_api_calls_per_day': 1000,
        'trial_period_days': 0,
        'is_trial_available': False,
        'is_default': True,
    },
)

# Create the public tenant
public_tenant, tenant_created = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={
        'name': 'Public Tenant 1',
        'code': 'PUBLIC1',
        'domain': 'hms-backend-l09g.onrender.com',
        # 'domain': 'localhost',
        'email': '1public@localhost',
        'phone': '+12345678903',
        'phone2': '',
        'address': 'System Address',
        'city': 'System City',
        'state': state,
        'lga': lga,
        'country': country,
        'facility_type': facility_type,
        'registration_number': 'SYS-001',
        'tax_id': '',
        'website': '',
        'subscription_plan': subscription_plan,
        'subscription_status': Tenant.SubscriptionStatus.TRIAL,
        'subscription_start_date': timezone.now().date(),
        'subscription_end_date': None,
        'monthly_fee': 0,
        'payment_method': '',
        'billing_email': '',
        'nhis_accreditation': Tenant.NHISAccreditation.NOT_APPLIED,
        'nhis_provider_id': '',
        'bed_capacity': 0,
        'established_date': None,
        'operating_hours': {},
        'emergency_services': False,
        'config': {},
        'features': {},
        'notes': 'System public tenant',
    },
)

# Create the domain for the public tenant
TenantDomain.objects.get_or_create(
    tenant=public_tenant,
    domain='hms-backend-l09g.onrender.com',
    # domain='localhost',
    defaults={'is_primary': True},
)

print('Setup complete.')
print(f'Country: {country.name} ({country.code})')
print(f'State: {state.name} ({state.code})')
print(f'LGA: {lga.name}')
print(f'Facility type: {facility_type.name}')
print(f'Subscription plan: {subscription_plan.name}')
print(f'Public tenant: {public_tenant.name} ({public_tenant.schema_name})')
print('Public domain: localhost')
