"""
Script to set up a test tenant with initial data for the Laboratory module.
Run this script after creating the database migrations and applying them.
"""
import os
import sys
import django

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcare_hms.settings')

django.setup()

from django.db import connection
from tenants.models import Tenant, TenantUser
from core.models import Country, State, LocalGovernmentArea, FacilityType, Specialization
from lab.models import LabTest


def setup_test_tenant():
    """Set up a test tenant with basic data."""
    
    print("Setting up test tenant...")
    
    # 1. Create or get Nigeria country
    country, created = Country.objects.get_or_create(
        name='Nigeria',
        defaults={
            'code': 'NG',
            'phone_code': '+234',
            'currency': 'NGN',
            'timezone': 'Africa/Lagos',
            'is_active': True
        }
    )
    if created:
        print(f"  Created country: {country.name}")
    else:
        print(f"  Country already exists: {country.name}")
    
    # 2. Create or get Lagos state
    state, created = State.objects.get_or_create(
        name='Lagos',
        country=country,
        defaults={'code': 'LA'}
    )
    if created:
        print(f"  Created state: {state.name}")
    else:
        print(f"  State already exists: {state.name}")
    
    # 3. Create or get Ikeja LGA
    lga, created = LocalGovernmentArea.objects.get_or_create(
        name='Ikeja',
        state=state,
        defaults={'code': 'IKJ'}
    )
    if created:
        print(f"  Created LGA: {lga.name}")
    else:
        print(f"  LGA already exists: {lga.name}")
    
    # 4. Create or get Facility Type
    facility_type, created = FacilityType.objects.get_or_create(
        name='General Hospital'
    )
    if created:
        print(f"  Created facility type: {facility_type.name}")
    else:
        print(f"  Facility type already exists: {facility_type.name}")
    
    # 5. Create or get Specialization
    specialization, created = Specialization.objects.get_or_create(
        name='General Medicine'
    )
    if created:
        print(f"  Created specialization: {specialization.name}")
    else:
        print(f"  Specialization already exists: {specialization.name}")
    
    # 6. Create or get Test Tenant
    tenant, created = Tenant.objects.get_or_create(
        code='TEST',
        defaults={
            'name': 'Test Hospital',
            'domain': 'test.smartcarehms.local',
            'email': 'info@testhospital.com',
            'phone': '+2348012345678',
            'address': '1 Test Road, Ikeja',
            'city': 'Ikeja',
            'state': state,
            'lga': lga,
            'country': country,
            'facility_type': facility_type,
            'is_active': True
        }
    )
    if created:
        print(f"  Created tenant: {tenant.name}")
    else:
        print(f"  Tenant already exists: {tenant.name}")
    
    # 7. Create tenant schema
    try:
        with connection.cursor() as cursor:
            schema_name = tenant.schema_name
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS {schema_name}')
            print(f"  Created schema: {schema_name}")
    except Exception as e:
        print(f"  Schema creation warning: {e}")
    
    # 8. Switch to tenant schema and create lab tests
    try:
        from django.db import connection
        connection.set_schema(tenant.schema_name)
        
        # Create lab tests
        lab_tests = [
            {
                'name': 'Complete Blood Count (CBC)',
                'code': 'CBC',
                'category': 'hematology',
                'sample_type': 'Blood (EDTA)',
                'turnaround_time': 2,
                'price': 2500.00,
                'reference_range': '4.5-11.0',
                'units': '10^9/L'
            },
            {
                'name': 'Liver Function Test',
                'code': 'LFT',
                'category': 'biochemistry',
                'sample_type': 'Blood (Serum)',
                'turnaround_time': 4,
                'price': 5000.00,
                'reference_range': 'See individual tests',
                'units': 'U/L'
            },
            {
                'name': 'Renal Function Test',
                'code': 'RFT',
                'category': 'biochemistry',
                'sample_type': 'Blood (Serum)',
                'turnaround_time': 4,
                'price': 4500.00,
                'reference_range': 'See individual tests',
                'units': 'mg/dL'
            },
            {
                'name': 'Malaria Parasite',
                'code': 'MP',
                'category': 'microbiology',
                'sample_type': 'Blood (Thick & Thin)',
                'turnaround_time': 1,
                'price': 1500.00,
                'reference_range': 'Negative',
                'units': ''
            },
            {
                'name': 'HIV Screening',
                'code': 'HIV',
                'category': 'immunology',
                'sample_type': 'Blood (Serum)',
                'turnaround_time': 2,
                'price': 2000.00,
                'reference_range': 'Non-reactive',
                'units': ''
            },
            {
                'name': 'Blood Glucose',
                'code': 'GLU',
                'category': 'biochemistry',
                'sample_type': 'Blood (Fluoride)',
                'turnaround_time': 1,
                'price': 1500.00,
                'reference_range': '70-100',
                'units': 'mg/dL',
                'critical_low': '40',
                'critical_high': '400'
            },
        ]
        
        for test_data in lab_tests:
            lab_test, test_created = LabTest.objects.get_or_create(
                code=test_data['code'],
                defaults={
                    'name': test_data['name'],
                    'category': test_data['category'],
                    'sample_type': test_data['sample_type'],
                    'turnaround_time': test_data['turnaround_time'],
                    'price': test_data['price'],
                    'reference_range': test_data['reference_range'],
                    'units': test_data['units'],
                    'critical_low': test_data.get('critical_low', ''),
                    'critical_high': test_data.get('critical_high', ''),
                }
            )
            if test_created:
                print(f"  Created lab test: {lab_test.name}")
        
        # Switch back to public schema
        connection.set_schema('public')
        
    except Exception as e:
        print(f"  Lab tests creation warning: {e}")
        try:
            connection.set_schema('public')
        except:
            pass
    
    # 9. Create admin user for tenant
    try:
        with connection.cursor() as cursor:
            schema_name = tenant.schema_name
            cursor.execute(f'SET search_path TO {schema_name}')
            
            admin_user, user_created = TenantUser.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@testhospital.com',
                    'first_name': 'System',
                    'last_name': 'Admin',
                    'phone': '+2348012345679',
                    'role': 'admin',
                    'employee_id': 'TEST001',
                    'is_staff': True,
                    'is_active': True,
                }
            )
            if user_created:
                admin_user.set_password('Test@123456')
                admin_user.save()
                print(f"  Created admin user: {admin_user.username}")
            else:
                print(f"  Admin user already exists: {admin_user.username}")
            
            cursor.execute('SET search_path TO public')
            
    except Exception as e:
        print(f"  Admin user creation warning: {e}")
    
    print("\n" + "="*50)
    print("Test tenant setup complete!")
    print("="*50)
    print(f"\nTenant Details:")
    print(f"  - Code: {tenant.code}")
    print(f"  - Name: {tenant.name}")
    print(f"  - Domain: {tenant.domain}")
    print(f"\nAdmin Credentials:")
    print(f"  - Username: admin")
    print(f"  - Password: Test@123456")
    print(f"\nTo access the API, configure your frontend to use:")
    print(f"  - API URL: http://localhost:9090/api/v1")
    print(f"  - Make sure to set the X-Tenant-ID header or configure tenant middleware")


if __name__ == '__main__':
    setup_test_tenant()
