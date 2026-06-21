from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

# Test public endpoint
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def test_public(request):
    return Response({'message': 'Public endpoint works!'})

# Swagger Schema View
schema_view = get_schema_view(
    openapi.Info(
        title="SmartCare HMS API",
        default_version='v1',
        description="SmartCare Healthcare Management System API Documentation",
        terms_of_service="https://smartcarehms.com/terms/",
        contact=openapi.Contact(email="support@smartcarehms.com"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Test public endpoint
    path('test-public/', test_public, name='test-public'),
    
    # API endpoints
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/core/', include('core.urls')),
    path('api/v1/tenants/', include('tenants.urls')),
    path('api/v1/patients/', include('patients.urls')),
    path('api/v1/clinical/', include('clinical.urls')),
    path('api/v1/pharmacy/', include('pharmacy.urls')),
    path('api/v1/lab/', include('lab.urls')),
    path('api/v1/billing/', include('billing.urls')),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)