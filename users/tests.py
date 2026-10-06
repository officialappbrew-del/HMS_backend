from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.conf import settings

from smartcare_hms.throttling import AuthenticationThrottle
from tenants.models import Tenant
from users.tasks import send_login_notification_email_task


class TenantWelcomeEmailQueueingTests(TestCase):
    @patch('superadmin.views.send_tenant_welcome_email_task.delay')
    def test_superadmin_tenant_creation_queues_welcome_email_in_background(self, mock_delay):
        from superadmin.views import TenantAdminCreateView

        payload = {
            'name': 'Beta Clinic',
            'domain': 'betaclinic.com',
            'email': 'beta@example.com',
            'phone': '+2348000000000',
            'address': '12 Main Road',
            'city': 'Lagos',
            'country': 1,
            'facility_type': 1,
            'registration_number': 'REG-2001',
            'subscription_plan': 1,
            'root_admin': {
                'first_name': 'Ada',
                'last_name': 'Green',
                'email': 'root@betaclinic.com',
                'password': 'StrongPass123!',
                'phone': '+2348000000001',
            },
        }

        request = type('RequestStub', (), {'data': payload, 'user': None})()

        fake_user = type(
            'FakeAdminUser',
            (),
            {
                'id': 11,
                'email': payload['root_admin']['email'],
                'username': 'ada.green',
                'first_name': payload['root_admin']['first_name'],
                'last_name': payload['root_admin']['last_name'],
                'phone': payload['root_admin']['phone'],
                'employee_id': 'ROOT-01',
                'is_root_admin': True,
                'get_full_name': lambda self: f"{payload['root_admin']['first_name']} {payload['root_admin']['last_name']}",
                'set_password': lambda self, value: None,
                'save': lambda self: None,
            },
        )()

        with patch.object(TenantAdminCreateView, 'get_permissions', return_value=[]):
            with patch('superadmin.views.TenantCreateSerializer') as mock_serializer, \
                 patch('superadmin.views.AuditLog.objects.create'), \
                 patch('superadmin.views.TenantUser.objects.filter') as mock_filter, \
                 patch('superadmin.views.TenantUser.objects.create', return_value=fake_user), \
                 patch('tenants.models.TenantSetting.objects.create'), \
                 patch('tenants.models.CommunicationProfile.objects.create'), \
                 patch('tenants.models.Department.objects.create'): 
                mock_filter.return_value.exists.return_value = False
                instance = mock_serializer.return_value
                instance.is_valid.return_value = True
                instance.validated_data = {'root_admin': payload['root_admin']}
                instance.save.return_value = None
                instance.instance = type(
                    'Tenant',
                    (),
                    {
                        'id': 99,
                        'name': payload['name'],
                        'domain': payload['domain'],
                        'public_id': 'abc-123',
                        'schema_name': 'beta_clinic',
                    },
                )()

                response = TenantAdminCreateView().post(request)

                self.assertEqual(response.status_code, 201)
                mock_delay.assert_called_once()


class AuthenticationThrottleTests(SimpleTestCase):
    def test_tenant_create_domain_accepts_frontend_urls_and_subdomains(self):
        from superadmin.serializers import TenantCreateSerializer

        self.assertEqual(
            TenantCreateSerializer().validate_domain('http://gcc.localhost:5173'),
            'gcc.localhost',
        )
        self.assertEqual(
            TenantCreateSerializer().validate_domain('https://lagosgeneral.example.com'),
            'lagosgeneral.example.com',
        )

    def test_authentication_throttle_allows_requests_without_crashing(self):
        throttle = AuthenticationThrottle()
        request = RequestFactory().post(
            '/api/v1/auth/login/',
            {'username': 'demo', 'password': 'secret'},
            HTTP_X_FORWARDED_FOR='203.0.113.10',
        )

        self.assertTrue(throttle.allow_request(request, None))

    def test_authentication_throttle_uses_submitted_username_as_identifier(self):
        throttle = AuthenticationThrottle()
        request = RequestFactory().post(
            '/api/v1/auth/login/',
            {'username': 'Demo', 'password': 'secret'},
            HTTP_X_FORWARDED_FOR='203.0.113.10',
        )

        cache_key = throttle.get_cache_key(request, None)
        self.assertIn('auth_user:demo', cache_key)


    @patch('users.tasks.send_mail')
    def test_global_admin_login_notification_uses_global_email_credentials(self, mock_send_mail):
        send_login_notification_email_task.run(
            recipient_email='admin@example.com',
            user_name='Global Admin',
            ip_address='203.0.113.10',
            user_agent='Mozilla/5.0',
            is_global_user=True,
        )

        mock_send_mail.assert_called_once()
        kwargs = mock_send_mail.call_args.kwargs
        self.assertEqual(kwargs['from_email'], settings.DEFAULT_FROM_EMAIL)
        self.assertIn('admin@example.com', kwargs['recipient_list'])

    @patch('users.tasks.threading.Thread')
    def test_queue_login_notification_starts_background_thread(self, mock_thread):
        from users.tasks import queue_login_notification

        queue_login_notification(
            recipient_email='admin@example.com',
            user_name='Global Admin',
            ip_address='203.0.113.10',
            user_agent='Mozilla/5.0',
            is_global_user=True,
        )

        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.return_value.start.called)

    @patch('users.tasks.logger.warning')
    @patch('users.tasks.send_login_notification_email_task.apply_async')
    def test_login_notification_broker_failure_is_best_effort(self, mock_apply_async, mock_warning):
        from users.tasks import _queue_login_notification_async

        mock_apply_async.side_effect = ConnectionError('broker unavailable')

        _queue_login_notification_async('admin@example.com', is_global_user=True)

        mock_warning.assert_called_once()


class TenantLoginIsolationTests(SimpleTestCase):
    def setUp(self):
        from users.views import AuthenticationView

        self.view = AuthenticationView()
        self.tenant = SimpleNamespace(
            code='XYZ7566',
            domain='xyz.localhost',
            schema_name='tenant_xyz7566',
            public_id='tenant-public-id',
            name='XYZ Clinic',
            subscription_status=Tenant.SubscriptionStatus.ACTIVE,
        )

    def test_only_header_aware_tenant_middleware_is_installed(self):
        self.assertIn('tenants.middleware.HeaderTenantMiddleware', settings.MIDDLEWARE)
        self.assertNotIn('django_tenants.middleware.main.TenantMainMiddleware', settings.MIDDLEWARE)

    def test_gar_employee_id_is_rejected_for_xyz_tenant(self):
        self.assertFalse(
            self.view._employee_id_matches_tenant('GAR-ADM-093551', self.tenant)
        )

    def test_host_tenant_overrides_stale_jwt_and_browser_tenant(self):
        from tenants.middleware import HeaderTenantMiddleware

        middleware = HeaderTenantMiddleware(lambda request: None)
        request = RequestFactory().get('/api/v1/patients/patients/', HTTP_HOST='xyz.localhost')
        with patch.object(middleware, '_resolve_tenant_from_host', return_value=self.tenant), \
             patch.object(middleware, '_resolve_tenant_from_user') as user_resolver, \
             patch.object(middleware, '_resolve_tenant_from_jwt') as jwt_resolver, \
             patch.object(middleware, '_resolve_tenant_from_header') as header_resolver, \
             patch('tenants.middleware.connection.set_tenant') as set_tenant:
            middleware.process_request(request)

        self.assertIs(request.tenant, self.tenant)
        user_resolver.assert_not_called()
        jwt_resolver.assert_not_called()
        header_resolver.assert_not_called()
        set_tenant.assert_called_once_with(self.tenant)

    def test_localhost_request_resolves_tenant_from_subdomain_header(self):
        from tenants.middleware import HeaderTenantMiddleware

        middleware = HeaderTenantMiddleware(lambda request: None)
        request = RequestFactory().get(
            '/api/v1/patients/patients/',
            HTTP_HOST='localhost:8000',
            HTTP_X_SUBDOMAIN='xyz',
        )
        with patch('tenants.middleware.Tenant.objects.filter') as tenant_filter:
            tenant_filter.return_value.first.return_value = self.tenant
            resolved = middleware._resolve_tenant_from_host(request)

        self.assertIs(resolved, self.tenant)
        self.assertIn('domain__iexact', str(tenant_filter.call_args))

    def test_render_host_resolves_full_tenant_domain_from_subdomain_header(self):
        from tenants.middleware import HeaderTenantMiddleware

        self.tenant.domain = 'hospitalmanager-beta.vercel.app'
        middleware = HeaderTenantMiddleware(lambda request: None)
        request = RequestFactory().get(
            '/api/v1/tenants/settings/current/',
            HTTP_HOST='hms-backend-l09g.onrender.com',
            HTTP_X_SUBDOMAIN='hospitalmanager-beta',
        )
        with patch('tenants.middleware.Tenant.objects.filter') as tenant_filter:
            tenant_filter.return_value.first.return_value = self.tenant

            resolved = middleware._resolve_tenant_from_host(request)

        self.assertIs(resolved, self.tenant)
        self.assertIn(
            "domain__istartswith",
            str(tenant_filter.call_args.args[0]),
        )

    def test_login_resolves_subdomain_from_configured_full_domain(self):
        self.tenant.domain = 'hospitalmanager-beta.vercel.app'
        with patch('users.views.Tenant.objects.filter') as tenant_filter:
            tenant_filter.return_value.first.return_value = self.tenant

            resolved = self.view._get_tenant_for_domain('hospitalmanager-beta')

        self.assertIs(resolved, self.tenant)
        self.assertIn(
            "domain__istartswith",
            str(tenant_filter.call_args.args[0]),
        )

    def test_tenant_login_filters_shared_user_table_by_tenant(self):
        request = RequestFactory().post('/api/v1/auth/login/')
        empty_queryset = MagicMock()
        empty_queryset.first.return_value = None
        empty_queryset.filter.return_value = empty_queryset

        with patch.object(self.view, '_get_tenant_for_domain', return_value=self.tenant), \
             patch('django.db.connection.set_schema'), \
             patch('users.views.TenantUser.objects.filter', return_value=empty_queryset) as user_filter:
            response = self.view.authenticate_tenant_user(
                {'user_id': 'mimam@example.com', 'password': 'wrong-password'},
                request,
                tenant_domain='xyz.localhost',
            )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(user_filter.call_args_list)
        self.assertTrue(all(call.kwargs.get('tenant') is self.tenant for call in user_filter.call_args_list))
