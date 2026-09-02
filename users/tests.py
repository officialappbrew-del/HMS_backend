from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase
from django.conf import settings

from smartcare_hms.throttling import AuthenticationThrottle
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
