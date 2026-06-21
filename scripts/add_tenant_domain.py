# add_tenant_domain.py
# Run inside Django shell: python manage.py shell < add_tenant_domain.py

from tenants.models import Tenant, TenantDomain

# Replace with your tenant's domain
tenant_domain = 'lagosgeneral.smartcarehms.local'

# Get the tenant by domain field
tenant = Tenant.objects.filter(domain=tenant_domain).first()

if not tenant:
    print(f"Tenant with domain '{tenant_domain}' not found!")
    print("Available tenants:")
    for t in Tenant.objects.all():
        print(f"  - {t.name}: {t.domain}")
else:
    print(f"Found tenant: {tenant.name} (ID: {tenant.id})")
    
    # Check if TenantDomain already exists
    existing_domain = TenantDomain.objects.filter(domain=tenant_domain).first()
    if existing_domain:
        print(f"TenantDomain already exists: {existing_domain.domain}")
    else:
        # Create TenantDomain
        tenant_domain_obj = TenantDomain.objects.create(
            domain=tenant_domain,
            tenant=tenant,
            is_primary=True
        )
        print(f"Created TenantDomain: {tenant_domain_obj.domain} for tenant {tenant.name}")
        print(f"Tenant schema: {tenant.schema_name}")
