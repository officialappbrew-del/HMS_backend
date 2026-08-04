from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core.permissions import IsFinanceStaff


class BillingPermissionTests(SimpleTestCase):
    def make_request(self, role):
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = type('UserStub', (), {
            'is_authenticated': True,
            'role': role,
            'is_superuser': False,
        })()
        return Request(request)

    def test_finance_permission_denies_receptionist(self):
        permission = IsFinanceStaff()
        request = self.make_request('receptionist')
        self.assertFalse(permission.has_permission(request, None))

    def test_finance_permission_allows_accountant(self):
        permission = IsFinanceStaff()
        request = self.make_request('accountant')
        self.assertTrue(permission.has_permission(request, None))
