from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from core.models import Country, FacilityType, LGA, State
from tenants.models import SubscriptionPlan, Tenant, TenantUser
from tenants.serializers import TenantInvitationSerializer
from tenants.views import TenantUserViewSet


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
