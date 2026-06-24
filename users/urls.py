from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    UserViewSet, AuthenticationView, TwoFAView,
    RSAKeyViewSet, UserSessionViewSet, SecurityEventViewSet,
    UserNotificationViewSet, TwoFASetupView, BackupCodeView,
    tenant_aware_token_refresh
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'rsa-keys', RSAKeyViewSet, basename='rsa-key')
router.register(r'sessions', UserSessionViewSet, basename='session')
router.register(r'security-events', SecurityEventViewSet, basename='security-event')
router.register(r'notifications', UserNotificationViewSet, basename='notification')

urlpatterns = [
    # Authentication endpoints
    path('login/', AuthenticationView.as_view(), name='login'),
    path('verify-2fa/', TwoFAView.as_view(), name='verify-2fa'),
    path('token/refresh/', tenant_aware_token_refresh, name='token_refresh'),
    
    # 2FA setup endpoints
    path('two-factor/setup/', TwoFASetupView.as_view(), name='two-factor-setup'),
    path('two-factor/backup-codes/', BackupCodeView.as_view(), name='two-factor-backup-codes'),
    
    # API routes
    path('', include(router.urls)),
]