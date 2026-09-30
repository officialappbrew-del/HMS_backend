from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from superadmin.views import _get_root_admins_per_tenant


class RootAdminLookupTests(SimpleTestCase):
    def test_root_admin_is_loaded_from_shared_table_by_tenant_id(self):
        tenants = [SimpleNamespace(id=17), SimpleNamespace(id=23)]
        root_admin = SimpleNamespace(id=3, tenant_id=17)
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        queryset.order_by.return_value = [root_admin]

        with patch('superadmin.views._ensure_public_schema') as ensure_public, \
             patch('superadmin.views.TenantUser.objects.filter', return_value=queryset) as user_filter:
            admins = _get_root_admins_per_tenant(tenants)

        self.assertIs(admins[17], root_admin)
        self.assertNotIn(23, admins)
        ensure_public.assert_called_once_with()
        user_filter.assert_called_once_with(tenant_id__in=[17, 23])
        queryset.filter.assert_called_once()