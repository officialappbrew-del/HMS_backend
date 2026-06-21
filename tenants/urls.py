from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import create_tenant_admin

from .views import (
    TenantViewSet, SubscriptionPlanViewSet, TenantUserViewSet,
    DepartmentViewSet, TenantSettingViewSet, TenantModuleViewSet,
    TenantInvitationViewSet, AcceptInvitationView,
    TenantActivityLogViewSet, TenantBackupViewSet,
    PublicTenantListView
)

router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'subscription-plans', SubscriptionPlanViewSet, basename='subscription-plan')
router.register(r'users', TenantUserViewSet, basename='tenant-user')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'settings', TenantSettingViewSet, basename='tenant-setting')
router.register(r'modules', TenantModuleViewSet, basename='tenant-module')
router.register(r'invitations', TenantInvitationViewSet, basename='tenant-invitation')
router.register(r'activity-logs', TenantActivityLogViewSet, basename='tenant-activity-log')
router.register(r'backups', TenantBackupViewSet, basename='tenant-backup')

urlpatterns = [
    path('', include(router.urls)),
    path('invitations/accept/', AcceptInvitationView.as_view(), name='accept-invitation'),
    path('tenants/<uuid:tenant_id>/create-admin/', create_tenant_admin, name='create-tenant-admin'),
    path('active-tenants/', PublicTenantListView.as_view(), name='public-tenant-list'),
]