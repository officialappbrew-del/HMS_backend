from django.db import connection
from django.test import TestCase

from core.models import Country, FacilityType
from tenants.models import SubscriptionPlan, Tenant
from .models import Ward, Bed, Admission
from .serializers import BedSerializer, WardSerializer, AdmissionSerializer


class AdmissionSerializerTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Nigeria', code='NG', phone_code='+234', currency='NGN', timezone='Africa/Lagos')
        facility_type = FacilityType.objects.create(name='Hospital', description='Test', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic',
            code='basic',
            description='Test plan',
            price_monthly=0,
            price_quarterly=0,
            price_yearly=0,
            currency='NGN',
            max_users=10,
            max_patients=100,
            max_storage_gb=1,
            max_api_calls_per_day=1000,
        )
        self.tenant = Tenant.objects.create(
            name='Test Facility',
            code='TF2',
            domain='test-facility-2.localhost',
            schema_name='test_facility_2',
            email='test2@example.com',
            phone='08000000001',
            address='Test address',
            city='Lagos',
            country=country,
            facility_type=facility_type,
            subscription_plan=subscription_plan,
            registration_number='REG124',
        )

    def test_serializer_creates_requested_admission(self):
        serializer = AdmissionSerializer(data={
            'patientId': 'PAT-100',
            'patientName': 'Ada Okafor',
            'source': 'Emergency Department',
            'diagnosis': 'Pneumonia',
            'preferredWardType': 'General Ward',
            'priority': 'High',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        admission = serializer.save(tenant=self.tenant)

        self.assertEqual(admission.status, 'Requested')
        self.assertEqual(admission.patient_id, 'PAT-100')
        self.assertEqual(admission.patient_name, 'Ada Okafor')
        self.assertEqual(admission.requestId, f'REQ{admission.id}')

    def test_serializer_accepts_snake_case_patient_fields(self):
        serializer = AdmissionSerializer(data={
            'patient_id': 'PAT-101',
            'patient_name': 'Bola Musa',
            'source': 'Referral',
            'diagnosis': 'Asthma',
            'preferred_ward_type': 'General Ward',
            'priority': 'Medium',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        admission = serializer.save(tenant=self.tenant)

        self.assertEqual(admission.patient_id, 'PAT-101')
        self.assertEqual(admission.patient_name, 'Bola Musa')

    def test_serializer_persists_discharge_summary_and_transfer_history(self):
        serializer = AdmissionSerializer(data={
            'patientId': 'PAT-102',
            'patientName': 'Bola Musa',
            'source': 'Referral',
            'diagnosis': 'Asthma',
            'preferredWardType': 'General Ward',
            'priority': 'Medium',
            'dischargeSummary': {
                'lengthOfStay': 4,
                'diagnosis': 'Asthma',
                'followUpInstructions': 'Review in 2 weeks'
            },
            'transferHistory': [{
                'toWardId': 'WARD-02',
                'toBedId': 'BED-02',
                'reason': 'Bed upgrade'
            }],
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        admission = serializer.save(tenant=self.tenant)

        self.assertEqual(admission.discharge_summary['followUpInstructions'], 'Review in 2 weeks')
        self.assertEqual(admission.transfer_history[0]['toWardId'], 'WARD-02')


class WardSerializerTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Nigeria', code='NG', phone_code='+234', currency='NGN', timezone='Africa/Lagos')
        facility_type = FacilityType.objects.create(name='Hospital', description='Test', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic',
            code='basic',
            description='Test plan',
            price_monthly=0,
            price_quarterly=0,
            price_yearly=0,
            currency='NGN',
            max_users=10,
            max_patients=100,
            max_storage_gb=1,
            max_api_calls_per_day=1000,
        )
        self.tenant = Tenant.objects.create(
            name='Test Facility',
            code='TF1',
            domain='test-facility.localhost',
            schema_name='test_facility',
            email='test@example.com',
            phone='08000000000',
            address='Test address',
            city='Lagos',
            country=country,
            facility_type=facility_type,
            subscription_plan=subscription_plan,
            registration_number='REG123',
        )

    def test_serializer_exposes_staff_count_and_bed_counts(self):
        ward = Ward(
            ward_id='W-001',
            ward_name='Male Ward',
            ward_type='General Ward',
            floor='1',
            supervisor='Nurse Ada',
            staff_count=4,
            total_beds=6,
            notes='Test ward',
        )

        data = WardSerializer(ward).data

        self.assertEqual(data['wardId'], 'W-001')
        self.assertEqual(data['wardName'], 'Male Ward')
        self.assertEqual(data['staffCount'], 4)
        self.assertEqual(data['totalBeds'], 6)

    def test_bed_serializer_accepts_ward_id_and_creates_related_ward(self):
        ward = Ward.objects.create(
            tenant=self.tenant,
            ward_id='W-100',
            ward_name='Test Ward',
            ward_type='General Ward',
            floor='1',
            supervisor='Nurse Ada',
            staff_count=2,
            total_beds=1,
        )

        serializer = BedSerializer(data={
            'bedId': 'W-100-B01',
            'bedNumber': 1,
            'bedType': 'Standard',
            'status': 'Available',
            'isPrivate': False,
            'cleaningStatus': 'Clean',
            'wardId': 'W-100',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        bed = serializer.save(tenant=self.tenant, ward=ward)

        self.assertEqual(bed.ward, ward)
        self.assertEqual(bed.bed_id, 'W-100-B01')

    def test_ward_and_bed_tables_exist_in_database(self):
        tables = connection.introspection.table_names()

        self.assertIn('ward_rounds_ward', tables)
        self.assertIn('ward_rounds_bed', tables)
