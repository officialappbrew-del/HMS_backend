#!/usr/bin/env python
"""Debug and fix patient password issues."""

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

def debug_patient_password():
    """Debug and fix patient password."""
    
    print("\n" + "="*60)
    print("PATIENT PASSWORD DEBUG & FIX")
    print("="*60)
    
    # Get the Garden City Clinic tenant
    tenant = Tenant.objects.filter(schema_name='tenant_gar5398').first()
    
    if not tenant:
        print("❌ Tenant not found: tenant_gar5398")
        return
    
    print(f"\nWorking with tenant: {tenant.name}")
    
    connection.set_schema(tenant.schema_name)
    try:
        # Find the patient
        patient = Patient.objects.filter(hospital_number='GAR5398-2026-100047').first()
        
        if not patient:
            print("❌ Patient not found")
            return
        
        print(f"\n✅ Found Patient: {patient.get_full_name()}")
        print(f"   Hospital Number: {patient.hospital_number}")
        print(f"   MRN: {patient.mrn}")
        print(f"   Login ID: {patient.login_id}")
        print(f"   Current Password Hash: {patient.password[:50]}..." if patient.password else "None")
        
        # Set a new password and save
        print(f"\n🔄 Setting new password: PatientPass123!")
        patient.set_password('PatientPass123!')
        patient.save(update_fields=['password'])
        
        print(f"✅ Password updated successfully")
        
        # Verify the password works
        is_valid = patient.check_password('PatientPass123!')
        print(f"✅ Password verification: {is_valid}")
        
        # Also ensure login_id is set correctly
        if not patient.login_id or patient.login_id != patient.hospital_number:
            print(f"\n🔄 Updating login_id to hospital_number: {patient.hospital_number}")
            patient.login_id = patient.hospital_number
            patient.save(update_fields=['login_id'])
            print(f"✅ Login ID updated")
        
        print(f"\n✅ PATIENT LOGIN CONFIGURED:")
        print(f"   Patient can now login with:")
        print(f"     - Identifier: {patient.login_id} (or {patient.hospital_number} or {patient.mrn})")
        print(f"     - Password: PatientPass123!")
        
    finally:
        connection.set_schema('public')
    
    print("\n" + "="*60)

if __name__ == '__main__':
    debug_patient_password()
