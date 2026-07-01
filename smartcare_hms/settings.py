"""
Django settings for SmartCare HMS project.
"""
import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
from decouple import config

# Import logging configuration
from .logging_config import setup_logging

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,admin.smartcarehms.local,lagosgeneral.smartcarehms.local,https://hms-backend-kmt1.onrender.com').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_yasg',
    'django_celery_beat',
    'django_celery_results',
    'django_redis',
    
    # Local apps
    'core',
    'users',
    'tenants',
    'patients',
    'clinical',
    'pharmacy',
    'lab',
    'billing',
    'emr',
    'cds',
    'audit',
    'ward_rounds',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'smartcare_hms.throttling.RateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_tenants.middleware.main.TenantMainMiddleware',  # Add this last
    'tenants.middleware.HeaderTenantMiddleware',  # Custom middleware for header-based tenant resolution
    
    # Logging middleware
    'smartcare_hms.logging_middleware.CorrelationIdMiddleware',
    'smartcare_hms.logging_middleware.EnrichLoggingContextMiddleware',
    'smartcare_hms.logging_middleware.RequestResponseLoggingMiddleware',
]

ROOT_URLCONF = 'smartcare_hms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartcare_hms.wsgi.application'

# Database
# For local development with PostgreSQL, use these settings:
# Make sure PostgreSQL is running (via docker-compose or local install)
DATABASE_URL = config('DATABASE_URL', default='postgres://postgres:password@localhost:5432/smartcare_hms')

# Parse the database URL
from urllib.parse import urlparse
db_url = urlparse(DATABASE_URL)

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': db_url.path[1:],  # Remove leading slash
        'USER': db_url.username,
        'PASSWORD': config('DB_PASSWORD', default='pluralsight'),
        'HOST': db_url.hostname,
        'PORT': db_url.port or 5432,
        'OPTIONS': {
            'sslmode': 'require' if 'render.com' in db_url.hostname else 'disable',
        },
    }
}



# For PostgreSQL (uncomment when ready)
# DATABASE_URL = config('DATABASE_URL', default='postgresql://hospital_ms_user:9VcytTw9HlVAID6PjaysFsCG6iroqTAw@dpg-d5uobgaqcgvc7391khrg-a.oregon-postgres.render.com/hospital_ms')
# DATABASES = {
#     'default': dj_database_url.parse(DATABASE_URL)
# }

# Custom user model
AUTH_USER_MODEL = 'users.GlobalUser'

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS settings
# Allow frontend origins to access the API
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config(
        'CORS_ALLOWED_ORIGINS',
        default='http://localhost:5173,http://localhost:9090'
    ).split(',')
    if origin.strip()
]

# Allow the custom tenant header and any other headers that browsers may request.
# Using '*' avoids preflight failures for custom headers such as x-tenant-id.
CORS_ALLOW_HEADERS = ['*']
CORS_PREFLIGHT_MAX_AGE = 86400

# CSRF settings (needed when frontend and backend are on different domains)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config(
        'CSRF_TRUSTED_ORIGINS',
        default='http://localhost:5173,http://localhost:9090'
    ).split(',')
    if origin.strip()
]
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'None'
CSRF_COOKIE_HTTPONLY = False

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT'
)

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'smartcare_hms.throttling.UserAPIThrottle',
        'smartcare_hms.throttling.AnonymousUserThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'api': '100/hour',
        'anon': '50/hour',
        'auth': '5/min',
        'password_reset': '3/hour',
        'password_reset_confirm': '5/hour',
        'login_attempt': '5/15min',
        '2fa': '5/15min',
        'audit': '1000/hour',
    }
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Cache settings (using local memory cache for development)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# For Redis cache (uncomment when ready)
# CACHES = {
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': config('REDIS_URL', default='redis://localhost:6379/0'),
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#         }
#     }
# }

# Session settings
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Changed for development
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Security settings
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default='false', cast=bool)

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Email settings - Send real emails in both development and production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@smartcarehms.local')
SERVER_EMAIL = config('SERVER_EMAIL', default='noreply@smartcarehms.local')

# Celery settings
if DEBUG:
    # Development: Use synchronous task execution (no broker needed)
    CELERY_TASK_ALWAYS_EAGER = True  # Execute tasks immediately instead of queueing
    CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='memory://')
else:
    # Production: Use Redis or RabbitMQ
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')

CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='django-db')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Encryption key for sensitive data
ENCRYPTION_KEY = config('ENCRYPTION_KEY', default='your-32-char-key-for-encryption-change-this')

# Swagger settings
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
    },
    'USE_SESSION_AUTH': False,
}

# Logging
# Disable Django's default logging configuration
LOGGING_CONFIG = None

# Enterprise-grade logging configuration
setup_logging(BASE_DIR, debug=DEBUG)

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB

# Application-specific settings
MAX_PATIENTS_PER_TENANT = 10000
MAX_USERS_PER_TENANT = 100

# Frontend URL for password reset links
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# Integration keys (optional)
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')
FLUTTERWAVE_SECRET_KEY = config('FLUTTERWAVE_SECRET_KEY', default='')
SMS_API_KEY = config('SMS_API_KEY', default='')

# Create logs directory if it doesn't exist
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Ensure media directory exists
MEDIA_ROOT.mkdir(exist_ok=True)

# Storage backend configuration (Supabase, S3, or local)
from .storage import *  # noqa: E402,F403


# Multi-tenancy settings
TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.TenantDomain"  # <-- fix here
PUBLIC_SCHEMA_NAME = 'public'
PUBLIC_SCHEMA_URLCONF = 'smartcare_hms.urls_public'
TENANT_SCHEMA_URLCONF = 'smartcare_hms.urls'
