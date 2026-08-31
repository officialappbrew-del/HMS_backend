from types import SimpleNamespace
from datetime import date

from django.test import TestCase
from rest_framework.test import APIRequestFactory
from django.utils import timezone
from django.core.files.base import ContentFile
from rest_framework.test import APIRequestFactory

from core.models import AuditLog, Country, FacilityType, LGA, State
from tenants.models import SubscriptionPlan, Tenant
from .models import Patient, PatientDocument, PatientMerge
from .services import merge_patients, unmerge_patient
from .serializers import PatientLoginSerializer, PatientSerializer
from .views import PatientViewSet


class PatientMRNGenerationTests(TestCase):
    def test_generate_mrn_returns_tenant_scoped_identifier(self):
        tenant = SimpleNamespace(code='LAG')
        patient_a = Patient(tenant=tenant)
        patient_b = Patient(tenant=tenant)

        mrn_a = patient_a.generate_mrn()
        mrn_b = patient_b.generate_mrn()

        self.assertIsInstance(mrn_a, str)
        self.assertIsInstance(mrn_b, str)
        self.assertEqual(mrn_a, f'LAG-{timezone.now().year}-100001')
        self.assertEqual(mrn_b, f'LAG-{timezone.now().year}-100002')
        self.assertNotEqual(mrn_a, mrn_b)

    def test_generate_hospital_number_uses_distinct_tenant_scoped_format(self):
        tenant = SimpleNamespace(code='LAG')
        patient = Patient(tenant=tenant)
        patient.mrn = patient.generate_mrn()

        hospital_number = patient.generate_hospital_number()

        self.assertEqual(hospital_number, f'LAG-{timezone.now().year}-100002')
        self.assertNotEqual(hospital_number, patient.mrn)


class PatientReceptionWorkflowTests(TestCase):
    def test_patient_model_supports_preferred_language(self):
        field = Patient._meta.get_field('preferred_language')

        self.assertEqual(field.max_length, 100)
        self.assertEqual(field.get_default(), 'English')


class PatientMPITests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        plan = SubscriptionPlan.objects.create(
            name='MPI', code='MPI', price_monthly=0, price_quarterly=0,
            price_yearly=0, currency='NGN', max_users=10, max_patients=100,
            max_storage_gb=5, trial_period_days=30,
        )
        self.tenant = Tenant.objects.create(
            name='MPI Clinic', code='MPI', domain='mpiclinic.localhost',
            schema_name='tenant_mpiclinic', email='mpi@example.com',
            phone='08011111111', address='1 MPI Street', city='Lagos',
            state=state, lga=lga, country=country, facility_type=facility_type,
            registration_number='REGMPI123', subscription_plan=plan,
        )
        self.source = Patient.objects.create(
            tenant=self.tenant, first_name='Jon', last_name='Doe',
            date_of_birth=date(1990, 1, 1), gender='male', phone='08022222222',
            email='jon@example.com', address='Lagos', state='Lagos', country='Nigeria',
        )
        self.survivor = Patient.objects.create(
            tenant=self.tenant, first_name='John', last_name='Doe',
            date_of_birth=date(1990, 1, 1), gender='male', phone='08033333333',
            email='john@example.com', address='Lagos', state='Lagos', country='Nigeria',
        )

    def test_merge_moves_linked_records_and_unmerge_restores_them(self):
        document = PatientDocument.objects.create(
            tenant=self.tenant, patient=self.source, document_type='other',
            title='Source chart note', file=ContentFile(b'source record', name='source.txt'),
        )
        merge_record = merge_patients(
            self.source.id, self.survivor.id, self.tenant,
            SimpleNamespace(), 'Duplicate registration with corrected spelling',
        )

        document.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(document.patient_id, self.survivor.id)
        self.assertEqual(self.source.merged_into_id, self.survivor.id)
        self.assertEqual(merge_record.status, 'active')
        self.assertEqual(len(merge_record.moved_records), 1)

        unmerge_patient(merge_record, SimpleNamespace())
        document.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(document.patient_id, self.source.id)
        self.assertIsNone(self.source.merged_into_id)
        self.assertEqual(PatientMerge.objects.get(pk=merge_record.pk).status, 'unmerged')


class PatientAuditTrailTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic',
            code='BASIC',
            price_monthly=0,
            price_quarterly=0,
            price_yearly=0,
            currency='NGN',
            max_users=10,
            max_patients=100,
            max_storage_gb=5,
            trial_period_days=30,
        )
        self.tenant = Tenant.objects.create(
            name='Audit Clinic',
            code='AUD',
            domain='auditclinic.localhost',
            schema_name='tenant_auditclinic',
            email='auditclinic@example.com',
            phone='08011111111',
            address='1 Audit Street',
            city='Lagos',
            state=state,
            lga=lga,
            country=country,
            facility_type=facility_type,
            registration_number='REGAUD123',
            subscription_plan=subscription_plan,
        )
        self.patient = Patient.objects.create(
            tenant=self.tenant,
            first_name='Grace',
            last_name='Bello',
            date_of_birth='1992-02-12',
            gender='female',
            phone='08022222222',
            email='grace@example.com',
            address='Surulere',
            state='Lagos',
            country='Nigeria',
        )

    def test_patient_retrieve_creates_view_patient_audit_log(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            role='admin',
            username='adminuser',
            email='admin@auditclinic.com',
            tenant_user=SimpleNamespace(tenant=self.tenant),
            get_full_name=lambda: 'Audit Admin',
        )
        request = APIRequestFactory().get(f'/api/v1/patients/{self.patient.id}/')
        request.user = user
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Test Browser'
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        response = PatientViewSet.as_view({'get': 'retrieve'})(request, pk=self.patient.id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                action='view_patient',
                resource_type='patient',
                resource_id=str(self.patient.id),
                tenant=self.tenant,
            ).exists()
        )

    def test_patient_audit_history_returns_patient_specific_entries(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            role='admin',
            username='adminuser',
            email='admin@auditclinic.com',
            tenant_user=SimpleNamespace(tenant=self.tenant),
            get_full_name=lambda: 'Audit Admin',
        )
        AuditLog.objects.create(
            tenant=self.tenant,
            user=None,
            actor='Audit Admin',
            action='view_patient',
            resource_type='patient',
            resource_id=str(self.patient.id),
            ip_address='127.0.0.1',
            user_agent='Mozilla/5.0 Test Browser',
        )
        request = APIRequestFactory().get(f'/api/v1/patients/{self.patient.id}/audit_history/')
        request.user = user
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Test Browser'
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        response = PatientViewSet.as_view({'get': 'audit_history'})(request, pk=self.patient.id)

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data.get('results', response.data)), 1)


class PatientPasswordRefreshActionTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        plan = SubscriptionPlan.objects.create(
            name='Basic', code='BASIC', price_monthly=0, price_quarterly=0,
            price_yearly=0, currency='NGN', max_users=10, max_patients=100,
            max_storage_gb=5, trial_period_days=30,
        )
        self.tenant = Tenant.objects.create(
            name='Refresh Clinic', code='REF', domain='refreshclinic.localhost',
            schema_name='tenant_refreshclinic', email='refresh@example.com',
            phone='08011111111', address='1 Refresh Street', city='Lagos',
            state=state, lga=lga, country=country, facility_type=facility_type,
            registration_number='REGREF123', subscription_plan=plan,
        )
        self.patient = Patient.objects.create(
            tenant=self.tenant,
            first_name='Refresh', last_name='Patient',
            date_of_birth=date(1995, 5, 6), gender='female',
            phone='08022222222', email='refreshpatient@example.com',
            address='Surulere', state='Lagos', country='Nigeria',
        )
        self.patient.set_password('OldPass123!')
        self.patient.save(update_fields=['password'])

    def test_patient_refresh_password_returns_new_password_and_updates_hash(self):
        user = SimpleNamespace(
            id=1,
            is_authenticated=True, is_active=True, is_superuser=False, is_staff=True,
            role='admin', tenant_user=SimpleNamespace(tenant=self.tenant),
            get_full_name=lambda: 'Refresh Admin',
        )
        request = APIRequestFactory().post(f'/api/v1/patients/patients/{self.patient.id}/refresh-password/')
        request.user = user
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Test Browser'
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        response = PatientViewSet.as_view({'post': 'refresh_password'})(request, pk=self.patient.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn('password', response.data)
        self.assertNotEqual(response.data['password'], 'OldPass123!')
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.check_password(response.data['password']))


class PatientPortalAuthTests(TestCase):
    def _create_patient(self, tenant):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        serializer = PatientSerializer(
            data={
                'tenant': tenant.id,
                'first_name': 'Ada',
                'last_name': 'Okafor',
                'date_of_birth': '1990-01-01',
                'gender': 'female',
                'phone': '08012345678',
                'email': 'ada@example.com',
                'address': 'Lagos',
                'state': 'Lagos',
                'country': 'Nigeria',
            },
            context={'request': request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.save()

    def _create_tenant(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic',
            code='BASIC',
            price_monthly=0,
            price_quarterly=0,
            price_yearly=0,
            currency='NGN',
            max_users=10,
            max_patients=100,
            max_storage_gb=5,
            trial_period_days=30,
        )
        return Tenant.objects.create(
            name='Test Clinic',
            code='TST',
            domain='testclinic.localhost',
            schema_name='tenant_testclinic',
            email='testclinic@example.com',
            phone='08000000000',
            address='1 Test Street',
            city='Lagos',
            state=state,
            lga=lga,
            country=country,
            facility_type=facility_type,
            registration_number='REG12345',
            subscription_plan=subscription_plan,
        )

    def test_patient_can_login_with_hospital_number_when_no_password_is_set(self):
        tenant = self._create_tenant()
        patient = self._create_patient(tenant)

        login_serializer = PatientLoginSerializer(data={
            'identifier': patient.hospital_number,
            'password': '',
        })

        self.assertTrue(login_serializer.is_valid(), login_serializer.errors)
        self.assertEqual(login_serializer.validated_data['patient'], patient)

    def test_patient_cannot_use_hospital_number_as_password_after_password_is_set(self):
        tenant = self._create_tenant()
        patient = self._create_patient(tenant)
        patient.set_password('secret-password')
        patient.save(update_fields=['password'])

        login_serializer = PatientLoginSerializer(data={
            'identifier': patient.hospital_number,
            'password': patient.hospital_number,
        })

        self.assertFalse(login_serializer.is_valid())
        self.assertIn('Invalid patient identifier or password.', str(login_serializer.errors))

    def test_patient_can_login_with_mrn_as_identifier_and_password_when_no_password_is_set(self):
        tenant = self._create_tenant()
        patient = self._create_patient(tenant)

        login_serializer = PatientLoginSerializer(data={
            'identifier': patient.mrn,
            'password': patient.mrn,
        })

        self.assertTrue(login_serializer.is_valid(), login_serializer.errors)
        self.assertEqual(login_serializer.validated_data['patient'], patient)
