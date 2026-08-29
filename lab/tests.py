from types import SimpleNamespace

from django.test import RequestFactory, TestCase
from django.utils import timezone

from datetime import date

from core.models import Country, FacilityType
from core.permissions import IsClinicalStaff, IsLabTechnician
from lab.models import LabTest
from lab.serializers import InstrumentMaintenanceSerializer, LabTestSerializer, LabOrderSerializer
from patients.models import Patient
from tenants.models import SubscriptionPlan, Tenant


class InstrumentMaintenanceSerializerTimezoneTests(TestCase):
    def test_scheduled_date_is_made_timezone_aware(self):
        serializer = InstrumentMaintenanceSerializer(
            data={
                'instrument_name': 'Chemistry Analyzer',
                'instrument_type': 'Analyzer',
                'maintenance_type': 'routine',
                'description': 'Routine servicing',
                'status': 'pending',
                'priority': 'high',
                'scheduled_date': '2026-09-05T00:00:00',
                'performed_by': 'Technician',
                'cost': '250.00',
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNotNone(serializer.validated_data['scheduled_date'])
        self.assertFalse(timezone.is_naive(serializer.validated_data['scheduled_date']))


class LabRolePermissionTests(TestCase):
    def test_lab_manager_has_lab_access(self):
        request = RequestFactory().get('/api/v1/lab/tests/')
        request.user = SimpleNamespace(is_authenticated=True, role='lab_manager')

        self.assertTrue(IsLabTechnician().has_permission(request, None))
        self.assertTrue(IsClinicalStaff().has_permission(request, None))


class LabTestSerializerTests(TestCase):
    def test_serializer_accepts_create_payload_without_explicit_tenant(self):
        serializer = LabTestSerializer(
            data={
                'name': 'Full Blood Count',
                'code': 'FBC-001',
                'category': 'hematology',
                'sample_type': 'Blood',
                'turnaround_time': 24,
                'price': '1500.00',
                'reference_range': '4.5-11.0',
                'units': 'x10^9/L',
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


class LabOrderSerializerTests(TestCase):
    def test_serializer_accepts_create_payload_without_explicit_order_number(self):
        country = Country.objects.create(name='Nigeria', code='NG', phone_code='+234', currency='NGN', timezone='Africa/Lagos', is_active=True)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP', description='General hospital')
        plan = SubscriptionPlan.objects.create(
            name='Starter',
            code='STARTER',
            price_monthly=10000,
            price_quarterly=25000,
            price_yearly=100000,
        )
        tenant = Tenant.objects.create(
            name='Test Facility',
            code='TFAC',
            domain='test-facility.localhost',
            schema_name='tenant_test_facility',
            email='admin@testfacility.com',
            phone='08000000000',
            address='Test address',
            city='Lagos',
            country=country,
            facility_type=facility_type,
            registration_number='REG-TEST-001',
            subscription_plan=plan,
        )
        patient = Patient.objects.create(
            tenant=tenant,
            hospital_number='H-1001',
            first_name='Ada',
            last_name='Test',
            date_of_birth=date(1990, 1, 1),
            gender='female',
            phone='08011111111',
            address='Test address',
            city='Lagos',
            state='Lagos',
            lga='Ikeja',
            country='Nigeria',
        )
        lab_test = LabTest.objects.create(
            tenant=tenant,
            name='Full Blood Count',
            code='FBC-001',
            category='hematology',
            sample_type='Blood',
            turnaround_time=24,
            price=1500,
        )

        serializer = LabOrderSerializer(
            data={
                'patient': patient.id,
                'test': lab_test.id,
                'priority': 'routine',
                'clinical_notes': 'Routine check',
                'status': 'ordered',
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
