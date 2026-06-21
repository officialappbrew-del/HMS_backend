"""
URL configuration for public schema.
This module is used by django-tenants for the public schema URLs.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import permissions
from tenants.views import PublicTenantListView

# Test public endpoint
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def test_public(request):
    return Response({'message': 'Public endpoint works!'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('test-public/', test_public, name='test-public'),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/core/', include('core.urls')),
    path('api/v1/tenants/', include('tenants.urls')),
    path('api/v1/tenants/active-tenants/', PublicTenantListView.as_view(), name='public-tenant-list'),
    path('api/v1/patients/', include('patients.urls')),
    path('api/v1/clinical/', include('clinical.urls')),
    path('api/v1/pharmacy/', include('pharmacy.urls')),
    path('api/v1/lab/', include('lab.urls')),
    path('api/v1/billing/', include('billing.urls')),
]
