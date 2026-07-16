from django.test import TestCase
from django.utils import timezone

from core.models import Country, FacilityType, LGA, State
from tenants.models import SubscriptionPlan, Tenant, TenantUser
from tenants.serializers import TenantInvitationSerializer


class TenantInvitationSerializerTests(TestCase):
    def test_invitation_serializer_allows_context_to_supply_tenant_and_invited_by(self):
        country = Country.objects.create(name='Nigeria', code='NG')
        state = State.objects.create(name='Lagos', code='LA', country=country)
        lga = LGA.objects.create(name='Ikeja', code='IK', state=state)
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
