from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core.permissions import IsClinicalStaff


class EMRPermissionTests(SimpleTestCase):
    def make_request(self, role):
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = type('UserStub', (), {
            'is_authenticated': True,
            'role': role,
            'is_superuser': False,
        })()
        return Request(request)

    def test_clinical_permission_denies_receptionist(self):
        permission = IsClinicalStaff()
        request = self.make_request('receptionist')
        self.assertFalse(permission.has_permission(request, None))

    def test_clinical_permission_allows_nurse(self):
        permission = IsClinicalStaff()
        request = self.make_request('nurse')
        self.assertTrue(permission.has_permission(request, None))
