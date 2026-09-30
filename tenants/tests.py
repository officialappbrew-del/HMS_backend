from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from core.models import Country, FacilityType, LGA, State
from tenants.models import SubscriptionPlan, Tenant, TenantUser
from tenants.communication import build_email_context, get_tenant_logo_url
from tenants.serializers import TenantInvitationSerializer
from tenants.views import TenantUserViewSet


class TenantLogoUrlTests(SimpleTestCase):
    def test_system_logo_url_is_used_before_tenant_logo(self):
        tenant = SimpleNamespace(
            settings_config=SimpleNamespace(
                system_logo=SimpleNamespace(url='/media/tenant_system_logos/web_hosting_on_namecheap.png')
            ),
            logo=SimpleNamespace(url='/media/tenant_logos/old-logo.png'),
        )
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f'http://localhost:8000{path}'
        )

        logo_url = get_tenant_logo_url(tenant, request=request)

        self.assertEqual(
            logo_url,
            'http://localhost:8000/media/tenant_system_logos/web_hosting_on_namecheap.png',
        )


class InvitationEmailTemplateTests(SimpleTestCase):
    def setUp(self):
        self.context = {
            'app_name': 'SmartCare HMS',
            'tenant_name': 'Garden City Clinic',
            'tenant_logo_url': 'http://localhost:8000/media/tenant_system_logos/clinic-logo.png',
            'year': 2026,
            'invitee_email': 'doctor@example.com',
            'inviter_name': 'Mimam Abraham',
            'role_label': 'Doctor',
            'registration_url': 'http://gcc.localhost:5173/invitation-signup?token=abc&data=xyz',
            'expires_at': timezone.now(),
            'invitation_message': 'Welcome to our team.',
            'invitee_name': 'Ada Doctor',
        }

    def test_invitation_email_uses_tenant_branding_and_registration_url(self):
        html = render_to_string('tenants/invitation_email.html', self.context)
        text = render_to_string('tenants/invitation_email.txt', self.context)

        self.assertIn('Garden City Clinic', html)
        self.assertIn(self.context['tenant_logo_url'], html)
        self.assertIn('Complete your account setup</a>', html)
        self.assertNotIn(self.context['registration_url'], html)
        self.assertIn('Complete your account setup:', text)
        self.assertIn(self.context['registration_url'], text)

    def test_created_account_email_explains_pending_approval(self):
        html = render_to_string('tenants/invitation_account_created_email.html', self.context)
        text = render_to_string('tenants/invitation_account_created_email.txt', self.context)

        self.assertIn('Pending hospital administrator approval', html)
        self.assertIn('Pending hospital administrator approval', text)

    def test_shared_email_context_provides_app_name_for_base_template(self):
        tenant = SimpleNamespace(name='Garden City Clinic', settings_config=None, logo=None)

        context = build_email_context(tenant)

        self.assertTrue(context['app_name'])


class TenantPasswordRefreshActionTests(TestCase):
    def test_staff_refresh_password_returns_new_password_and_updates_hash(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic', code='basic', price_monthly=10000,
            price_quarterly=25000, price_yearly=100000,
        )
        tenant = Tenant.objects.create(
            name='Refresh Hospital', code='RH1', domain='refreshhospital.localhost',
            schema_name='tenant_refreshhospital', email='info@refreshhospital.com',
            phone='08000000000', address='1 Test Street', city='Lagos',
            state=state, lga=lga, country=country, facility_type=facility_type,
            registration_number='REG-REF-001', subscription_plan=subscription_plan,
        )
        user = TenantUser.objects.create(
            tenant=tenant, username='refresh-admin', email='admin@refreshhospital.com',
            password='old-password', first_name='Refresh', last_name='Admin',
            phone='08011111111', role='admin',
        )
        user.set_password('OldPass123!')
        user.save(update_fields=['password'])

        request = APIRequestFactory().post(f'/api/v1/tenants/users/{user.id}/refresh-password/')
        request.user = SimpleNamespace(
            id=user.id,
            is_authenticated=True, is_active=True, is_superuser=False, is_staff=True,
            role='admin', tenant_user=SimpleNamespace(tenant=tenant),
            get_full_name=lambda: 'Refresh Admin',
        )
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Test Browser'
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        response = TenantUserViewSet.as_view({'post': 'refresh_password'})(request, pk=user.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn('password', response.data)
        self.assertNotEqual(response.data['password'], 'OldPass123!')
        user.refresh_from_db()
        self.assertTrue(user.check_password(response.data['password']))

    def test_non_root_admin_cannot_refresh_staff_password(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic', code='basic', price_monthly=10000,
            price_quarterly=25000, price_yearly=100000,
        )
        tenant = Tenant.objects.create(
            name='Restricted Hospital', code='RH2', domain='restrictedhospital.localhost',
            schema_name='tenant_restrictedhospital', email='info@restrictedhospital.com',
            phone='08000000001', address='1 Test Street', city='Lagos',
            state=state, lga=lga, country=country, facility_type=facility_type,
            registration_number='REG-REF-002', subscription_plan=subscription_plan,
        )
        user = TenantUser.objects.create(
            tenant=tenant, username='regular-user', email='regular@restrictedhospital.com',
            password='old-password', first_name='Regular', last_name='User',
            phone='08011111112', role='doctor',
        )
        user.set_password('OldPass123!')
        user.save(update_fields=['password'])

        request = APIRequestFactory().post(f'/api/v1/tenants/users/{user.id}/refresh-password/')
        request.user = SimpleNamespace(
            id=99,
            is_authenticated=True, is_active=True, is_superuser=False, is_staff=True,
            role='doctor', tenant_user=SimpleNamespace(tenant=tenant, is_root_admin=False),
            get_full_name=lambda: 'Regular User',
        )
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Test Browser'
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        response = TenantUserViewSet.as_view({'post': 'refresh_password'})(request, pk=user.id)

        self.assertEqual(response.status_code, 403)


class TenantInvitationSerializerTests(TestCase):
    def test_invitation_serializer_allows_context_to_supply_tenant_and_invited_by(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', state=state)
        facility_type = FacilityType.objects.create(name='Hospital', code='HOSP')
        subscription_plan = SubscriptionPlan.objects.create(
            name='Basic',
            code='basic',
            price_monthly=10000,
            price_quarterly=25000,
            price_yearly=100000,
        )

        tenant = Tenant.objects.create(
            name='Test Hospital',
            code='TH1',
            domain='testhospital.localhost',
            schema_name='tenant_testhospital',
            email='info@testhospital.com',
            phone='08000000000',
            address='1 Test Street',
            city='Lagos',
            state=state,
            lga=lga,
            country=country,
            facility_type=facility_type,
            registration_number='REG-001',
            subscription_plan=subscription_plan,
        )

        TenantUser.objects.create(
            tenant=tenant,
            username='admin',
            email='admin@testhospital.com',
            password='test-password',
            first_name='Admin',
            last_name='User',
            phone='08011111111',
            role='admin',
        )

        serializer = TenantInvitationSerializer(
            data={
                'email': 'newstaff@testhospital.com',
                'role': 'doctor',
                'expires_at': (timezone.now() + timezone.timedelta(days=2)).isoformat(),
                'message': 'Welcome aboard',
            },
            context={'tenant': tenant},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
