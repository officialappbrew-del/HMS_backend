from django.db import connection
from django.test import TestCase
from rest_framework import viewsets

from core.models import Country, FacilityType
from tenants.models import SubscriptionPlan, Tenant
from .emergency_api import EmergencyCallViewSet
from .models import Ward, Bed, Admission
from .serializers import BedSerializer, WardSerializer, AdmissionSerializer, DutyRosterSerializer, LeaveRequestSerializer, PerformanceAppraisalSerializer


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


class EmergencyApiViewSetTests(TestCase):
    def test_dispatch_method_is_not_shadowed_by_emergency_action(self):
        self.assertIs(EmergencyCallViewSet.dispatch, viewsets.ViewSet.dispatch)


class RosterPerformanceSerializerTests(TestCase):
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
            code='TF3',
            domain='test-facility-3.localhost',
            schema_name='test_facility_3',
            email='test3@example.com',
            phone='08000000002',
            address='Test address',
            city='Lagos',
            country=country,
            facility_type=facility_type,
            subscription_plan=subscription_plan,
            registration_number='REG125',
        )

    def test_duty_roster_serializer_creates_assignments(self):
        serializer = DutyRosterSerializer(data={
            'month': 'January',
            'year': 2026,
            'department': 'Internal Medicine',
            'status': 'Draft',
            'assignments': [{
                'staffId': 'DR001',
                'staffName': 'Dr. Ada Okafor',
                'date': '2026-01-05',
                'dutyType': 'Call Duty',
                'startTime': '20:00',
                'endTime': '08:00',
                'notes': 'Emergency cover'
            }],
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        roster = serializer.save(tenant=self.tenant)
        self.assertEqual(roster.assignments.count(), 1)
        self.assertEqual(roster.assignments.first().staff_id, 'DR001')

    def test_duty_roster_serializer_update_preserves_untouched_assignments(self):
        roster = DutyRosterSerializer(data={
            'month': 'January',
            'year': 2026,
            'department': 'Internal Medicine',
            'status': 'Draft',
            'assignments': [
                {
                    'staffId': 'DR001',
                    'staffName': 'Dr. Ada Okafor',
                    'date': '2026-01-05',
                    'dutyType': 'Call Duty',
                    'startTime': '07:00',
                    'endTime': '19:00',
                    'notes': 'Primary ward' 
                },
                {
                    'staffId': 'DR002',
                    'staffName': 'Dr. Bassey',
                    'date': '2026-01-06',
                    'dutyType': 'Night Duty',
                    'startTime': '19:00',
                    'endTime': '07:00',
                    'notes': 'Backup' 
                }
            ]
        })
        self.assertTrue(roster.is_valid(), roster.errors)
        saved_roster = roster.save(tenant=self.tenant)

        update_payload = {
            'month': 'January',
            'year': 2026,
            'department': 'Internal Medicine',
            'status': 'Draft',
            'assignments': [{
                'id': saved_roster.assignments.first().id,
                'staffId': 'DR001',
                'staffName': 'Dr. Ada Okafor',
                'date': '2026-01-05',
                'dutyType': 'Call Duty',
                'startTime': '07:00',
                'endTime': '19:00',
                'notes': 'Updated primary ward'
            }]
        }

        serializer = DutyRosterSerializer(instance=saved_roster, data=update_payload, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_roster = serializer.save()

        self.assertEqual(updated_roster.assignments.count(), 2)
        self.assertEqual(updated_roster.assignments.filter(staff_id='DR002').count(), 1)

    def test_performance_appraisal_serializer_creates_with_camel_case_fields(self):
        serializer = PerformanceAppraisalSerializer(data={
            'staffId': 'DR001',
            'staffName': 'Dr. Ada Okafor',
            'appraisalYear': 2026,
            'period': 'Jan-Dec 2026',
            'rater': 'Dr. Bassey',
            'rating': 4.5,
            'clinicalExcellence': 4.7,
            'patientCare': 4.8,
            'teamwork': 4.2,
            'leadership': 4.3,
            'continuousLearning': 4.6,
            'overallComments': 'Excellent',
            'status': 'Completed',
            'date': '2026-01-15',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        appraisal = serializer.save(tenant=self.tenant)
        self.assertEqual(appraisal.staff_id, 'DR001')
        self.assertEqual(appraisal.overall_comments, 'Excellent')


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
