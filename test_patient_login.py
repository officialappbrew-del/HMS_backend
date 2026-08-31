#!/usr/bin/env python
"""Test script to verify patient login functionality."""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcare_hms.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from django.db import connection
from patients.models import Patient
from tenants.models import Tenant

def test_patient_login():
    """Test patient login with a known patient."""
    
    print("\n" + "="*60)
    print("PATIENT LOGIN TEST")
    print("="*60)
    
    # Get active tenants
    active_tenants = Tenant.objects.filter(
        subscription_status__in=[
            Tenant.SubscriptionStatus.ACTIVE,
            Tenant.SubscriptionStatus.TRIAL,
        ]
    )
    
    print(f"\nFound {active_tenants.count()} active tenants")
    
    for tenant in active_tenants:
        print(f"\n--- Tenant: {tenant.name} ({tenant.schema_name}) ---")
        
        connection.set_schema(tenant.schema_name)
        try:
            # Get all patients
            patients = Patient.objects.filter().values(
                'id', 'hospital_number', 'mrn', 'login_id', 'first_name', 'last_name', 'password'
            )[:5]
            
            print(f"Patients in {tenant.name}:")
            for patient in patients:
                has_password = bool(patient['password'])
                print(f"  - {patient['hospital_number']} | MRN: {patient['mrn']} | Login ID: {patient['login_id']} | Password: {has_password}")
            
            # Try to find and test the specific MRN
            specific_patient = Patient.objects.filter(
                hospital_number='GAR5398-2026-100047'
            ).first()
            
            if specific_patient:
                print(f"\n✅ Found patient: {specific_patient.get_full_name()}")
                print(f"   Hospital Number: {specific_patient.hospital_number}")
                print(f"   MRN: {specific_patient.mrn}")
                print(f"   Login ID: {specific_patient.login_id}")
                print(f"   Password Set: {bool(specific_patient.password)}")
                
                # Test password
                test_password = 'PatientPass123!'
                if specific_patient.password:
                    is_valid = specific_patient.check_password(test_password)
                    print(f"   Password Match ('{test_password}'): {is_valid}")
                    
                    if is_valid:
                        print(f"\n✅ LOGIN TEST PASSED!")
                        print(f"   Patient can login with:")
                        print(f"     - user_id: {specific_patient.hospital_number}")
                        print(f"     - password: {test_password}")
                    else:
                        print(f"\n❌ LOGIN TEST FAILED - Password doesn't match")
                else:
                    print(f"\n❌ No password set for patient!")
            else:
                print(f"\n❌ Patient not found: GAR5398-2026-100047")
            
        finally:
            connection.set_schema('public')
    
    print("\n" + "="*60)

if __name__ == '__main__':
    test_patient_login()
