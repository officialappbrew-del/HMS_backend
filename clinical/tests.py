from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from patients.models import Patient, PatientVisit
from tenants.models import Tenant, TenantUser
from .models import Prescription


class PrescriptionWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='Test Tenant', domain='test-tenant')
        self.user = get_user_model().objects.create_user(username='doctor', email='doctor@example.com', password='password123')
        self.tenant_user = TenantUser.objects.create(
            user=self.user,
            tenant=self.tenant,
            role='doctor',
            first_name='Doc',
            last_name='Test',
        )
        self.user.tenant_user = self.tenant_user
        self.patient = Patient.objects.create(
            tenant=self.tenant,
            first_name='Jane',
            last_name='Doe',
            date_of_birth='1990-01-01',
        )
        self.visit = PatientVisit.objects.create(
            tenant=self.tenant,
            patient=self.patient,
            visit_number='V-001',
            status='active',
        )
        self.prescription = Prescription.objects.create(
            tenant=self.tenant,
            visit=self.visit,
            patient=self.patient,
            drug_name='Warfarin',
            dosage='5mg',
            frequency='Daily',
            duration='7 days',
            route='oral',
            prescribed_by=self.tenant_user,
        )
        self.client.force_authenticate(user=self.user)

    def test_medication_history_and_interaction_check(self):
        response = self.client.get(f'/api/v1/clinical/prescriptions/history/?patient={self.patient.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['patient_id'], self.patient.id)
        self.assertEqual(body['medications'][0]['drug_name'], 'Warfarin')

        interaction_response = self.client.post('/api/v1/clinical/prescriptions/interaction-check/', {
            'drug_names': ['Warfarin', 'Aspirin'],
        }, format='json')
        self.assertEqual(interaction_response.status_code, status.HTTP_200_OK)
        self.assertTrue(interaction_response.json()['interactions'])

    def test_duplicate_medication_history_generates_duplicate_warning(self):
        Prescription.objects.create(
            tenant=self.tenant,
            visit=self.visit,
            patient=self.patient,
            drug_name='Warfarin',
            dosage='5mg',
            frequency='Daily',
            duration='14 days',
            route='oral',
            prescribed_by=self.tenant_user,
        )

        response = self.client.get(f'/api/v1/clinical/prescriptions/history/?patient={self.patient.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        warnings = response.json().get('warnings', [])
        self.assertTrue(any(item.get('type') == 'duplicate_drug' for item in warnings))
