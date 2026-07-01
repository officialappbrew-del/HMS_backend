from django.test import RequestFactory, SimpleTestCase

from smartcare_hms.throttling import AuthenticationThrottle


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
