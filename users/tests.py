from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.conf import settings

from smartcare_hms.throttling import AuthenticationThrottle
from users.tasks import send_login_notification_email_task


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
