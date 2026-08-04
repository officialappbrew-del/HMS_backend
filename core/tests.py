from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from billing.models import Invoice
from clinical.models import Prescription
from patients.models import Patient, PatientVisit
from pharmacy.models import Drug
from tenants.models import Department, SubscriptionPlan, Tenant, TenantUser
from .models import FacilityType, Specialization, Country, State, LGA, AuditLog


class DashboardInsightsViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.country = Country.objects.create(name='Nigeria', code='NG', phone_code='+234', currency='NGN', timezone='Africa/Lagos')
        self.state = State.objects.create(name='Rivers', code='RI', country=self.country)
        self.lga = LGA.objects.create(name='Port Harcourt', state=self.state)
        self.facility_type = FacilityType.objects.create(name='Hospital', description='General', code='HOSP')
        self.subscription_plan = SubscriptionPlan.objects.create(
            name='Basic', code='basic', price_monthly=1000, price_quarterly=2500, price_yearly=9000,
            currency='NGN', max_users=10, max_patients=1000, max_storage_gb=5,
            trial_period_days=30, is_trial_available=True
        )
        self.tenant = Tenant.objects.create(
            name='Test Hospital', code='THS', domain='test-hospital.localhost', schema_name='test_hospital',
            email='admin@test-hospital.localhost', phone='08000000000', address='1 Test Street', city='Port Harcourt',
            state=self.state, lga=self.lga, country=self.country, facility_type=self.facility_type,
            registration_number='REG-001', subscription_plan=self.subscription_plan
        )
        self.global_user = self.user_model.objects.create_user(
            username='doctor1', email='doctor1@test-hospital.localhost', password='StrongPass123!', role='system_admin'
        )
        self.tenant_user = TenantUser.objects.create(
            tenant=self.tenant, username='doctor1', email='doctor1@test-hospital.localhost', password='hashed',
            first_name='Ada', last_name='Jones', phone='08011111111', role='doctor', department=None,
            global_user=self.global_user
        )
        self.global_user.tenant_user = self.tenant_user
        self.global_user.save(update_fields=['tenant_user'])

        self.patient = Patient.objects.create(
            tenant=self.tenant, hospital_number='THS-001', login_id='THS-001', first_name='Jane', last_name='Doe',
            date_of_birth='1990-01-01', gender='female', phone='08022222222', address='Test address',
            city='Port Harcourt', state='Rivers', lga='Port Harcourt', country='Nigeria', registered_by=self.tenant_user
        )
        self.visit = PatientVisit.objects.create(
            tenant=self.tenant, patient=self.patient, visit_number='VIS-001', chief_complaint='Headache',
            doctor=self.tenant_user, nurse=self.tenant_user, visit_status='waiting'
        )
        self.drug = Drug.objects.create(
            tenant=self.tenant, name='Paracetamol', generic_name='Paracetamol', drug_code='PARA001', category='analgesic',
            form='tablet', stock_quantity=5, reorder_level=10, reorder_quantity=20,
            unit_price=5, selling_price=10, unit_of_measure='tablet', status='active'
        )
        self.prescription = Prescription.objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient, drug_name='Paracetamol', dosage='1 tablet',
            frequency='daily', duration='3 days', status='prescribed', prescribed_by=self.tenant_user
        )
        self.invoice = Invoice.objects.create(
            tenant=self.tenant, patient=self.patient, visit=self.visit, due_date='2099-01-01', subtotal=5000, tax_amount=0,
            discount_amount=0, total_amount=5000, amount_paid=0, balance_due=5000, status='issued', insurance_covered=False,
            insurance_amount=0, patient_amount=5000, created_by='test'
        )

    def test_doctor_dashboard_insights_are_returned_for_tenant(self):
        self.client.force_authenticate(user=self.global_user)
        response = self.client.get(reverse('dashboard-insights-list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role'], 'doctor')
        self.assertIn('summary', response.data)
        self.assertGreaterEqual(len(response.data['alerts']), 1)
        self.assertGreaterEqual(len(response.data['tasks']), 1)

    def test_audit_logs_are_returned_newest_first(self):
        self.client.force_authenticate(user=self.global_user)

        older = AuditLog.objects.create(
            tenant=self.tenant,
            user=self.global_user,
            action='login',
            resource_type='user',
            resource_id='u-older',
            title='Older login',
            actor='Ada Jones',
        )
        newer = AuditLog.objects.create(
            tenant=self.tenant,
            user=self.global_user,
            action='logout',
            resource_type='user',
            resource_id='u-newer',
            title='Newer logout',
            actor='Ada Jones',
        )

        response = self.client.get(reverse('audit-log-list'))

        self.assertEqual(response.status_code, 200)
        ids = [item['id'] for item in response.data['results']]
        self.assertIn(newer.id, ids)
        self.assertIn(older.id, ids)
        self.assertLess(ids.index(older.id), ids.index(newer.id))
