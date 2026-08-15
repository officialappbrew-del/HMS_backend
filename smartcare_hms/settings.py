"""
Django settings for SmartCare HMS project.
"""
"""
Django settings for SmartCare HMS project.
"""
import os
import sys
import importlib

# ============================================
# PATCH: Fix pkg_resources for Python 3.14+
# ============================================
try:
    import pkg_resources
except ModuleNotFoundError:
    print("WARNING: pkg_resources not found, creating mock in settings...")
    
    class MockPkgResources:
        @staticmethod
        def get_distribution(name):
            try:
                import importlib.metadata
                return importlib.metadata.distribution(name)
            except:
                return None
        
        @staticmethod
        def require(name):
            pass
        
        @staticmethod
        def iter_entry_points(group, name=None):
            try:
                from importlib.metadata import entry_points
                eps = entry_points().select(group=group)
                if name:
                    eps = eps.select(name=name)
                return eps
            except:
                return []
        
        @staticmethod
        def parse_version(version):
            try:
                from packaging.version import Version
                return Version(version)
            except:
                return version
    
    mock_module = type('pkg_resources', (), {})()
    for attr in dir(MockPkgResources):
        if not attr.startswith('_'):
            setattr(mock_module, attr, getattr(MockPkgResources, attr))
    
    sys.modules['pkg_resources'] = mock_module
    
    # Add exceptions
    class DistributionNotFound(Exception):
        pass
    
    class VersionConflict(Exception):
        pass
    
    setattr(sys.modules['pkg_resources'], 'DistributionNotFound', DistributionNotFound)
    setattr(sys.modules['pkg_resources'], 'VersionConflict', VersionConflict)
    
    print("OK: Created mock pkg_resources module in settings")

# ============================================
# Continue with normal settings
# ============================================
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse
import dj_database_url
from decouple import config
import os
import sys
import logging

# Import logging configuration
from .logging_config import setup_logging

# ============================================
# SENTRY ERROR MONITORING
# ============================================
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        profiles_sample_rate=config('SENTRY_PROFILES_SAMPLE_RATE', default=0.1, cast=float),
        send_default_pii=False,
        environment=config('SENTRY_ENVIRONMENT', default='production' if not DEBUG else 'development'),
    )

# ============================================
# BASE DIRECTORY
# ============================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SECURITY
# ============================================
DEBUG = config('DEBUG', default=False, cast=bool)

# In production, fail fast if the secret key is left at an insecure default.
_SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')
if (not DEBUG) and _SECRET_KEY in {
    'django-insecure-change-this-in-production',
    'changeme',
    'secret',
    'password',
}:
    raise RuntimeError(
        '🚨 SECRET_KEY is insecure/missing. Set a strong SECRET_KEY in production '
        'before starting the server. Refusing to boot with an insecure key.'
    )
SECRET_KEY = _SECRET_KEY

# ============================================
# APPLICATION IDENTITY
# ============================================
APP_NAME = config('APP_NAME', default='SmartCare HMS')

# ============================================
# ALLOWED HOSTS - tightened per environment
# ============================================
# Only allow known hosts. In production always set ALLOWED_HOSTS explicitly.
_DEFAULT_ALLOWED_HOSTS = 'localhost,127.0.0.1' if DEBUG else 'hms-backend-kmt1.onrender.com,admin.smartcarehms.local,lagosgeneral.smartcarehms.local'
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=_DEFAULT_ALLOWED_HOSTS).split(',')

# ============================================
# APPLICATION DEFINITION
# ============================================
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
    'ndpr',
    'integration',
    'superadmin',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'smartcare_hms.admin_security.AdminIPRestrictMiddleware',
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

# ============================================
# URLS & TEMPLATES
# ============================================
ROOT_URLCONF = 'smartcare_hms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        # APP_DIRS must be False when 'loaders' is explicitly defined below.
        # These two options are mutually exclusive in Django.
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'smartcare_hms.context_processors.app_name',
            ],
            # Standard (non-cached) loaders in DEBUG so templates hot-reload.
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ] if DEBUG else [
                # Cache compiled templates in production to avoid re-compiling
                # on every render.
                (
                    'django.template.loaders.cached.Loader',
                    [
                        'django.template.loaders.filesystem.Loader',
                        'django.template.loaders.app_directories.Loader',
                    ],
                )
            ],
        },
    },
]

WSGI_APPLICATION = 'smartcare_hms.wsgi.application'

# ============================================
# DATABASE CONFIGURATION (Dynamic)
# ============================================

# Get the database mode from environment
DATABASE_MODE = config('DATABASE_MODE', default='local')

# Define database configurations
DATABASE_CONFIGS = {
    'local': {
        'url_key': 'LOCAL_DATABASE_URL',
        'password_key': 'LOCAL_DB_PASSWORD',
        'ssl_mode': 'disable',
        'label': 'Local PostgreSQL'
    },
    'render': {
        'url_key': 'RENDER_DATABASE_URL',
        'password_key': 'RENDER_DB_PASSWORD',
        'ssl_mode': 'require',
        'label': 'Render PostgreSQL'
    },
    'aws': {
        'url_key': 'AWS_DATABASE_URL',
        'password_key': 'AWS_DB_PASSWORD',
        'ssl_mode': 'require',
        'label': 'AWS RDS PostgreSQL'
    },
    'custom': {
        'url_key': 'CUSTOM_DATABASE_URL',
        'password_key': 'CUSTOM_DB_PASSWORD',
        'ssl_mode': 'require',
        'label': 'Custom PostgreSQL'
    }
}

# Function to get database configuration
def get_database_config(mode):
    """Get database configuration for the specified mode"""
    config_info = DATABASE_CONFIGS.get(mode, DATABASE_CONFIGS['local'])
    
    # Get the URL and password from environment
    db_url = config(config_info['url_key'], default='')
    db_password = config(config_info['password_key'], default='')
    
    # If URL is empty, fallback to local
    if not db_url:
        logger = logging.getLogger(__name__)
        logger.warning(f"⚠️  Database URL for '{mode}' not found. Falling back to local.")
        config_info = DATABASE_CONFIGS['local']
        db_url = config('LOCAL_DATABASE_URL', default='postgresql://postgres:pluralsight@localhost:5432/HMS_DB')
        db_password = config('LOCAL_DB_PASSWORD', default='pluralsight')
    
    return {
        'url': db_url,
        'password': db_password,
        'ssl_mode': config_info['ssl_mode'],
        'label': config_info['label']
    }

# Get active database config
active_db = get_database_config(DATABASE_MODE)
DATABASE_URL = active_db['url']
DB_PASSWORD = active_db['password']
DB_SSL_MODE = active_db['ssl_mode']

# Parse the database URL
db_url = urlparse(DATABASE_URL)

# Extract database components
db_name = db_url.path[1:] if db_url.path else 'HMS_DB'
db_user = db_url.username or 'postgres'
db_host = db_url.hostname or 'localhost'
db_port = db_url.port or 5432

# Database configuration for django-tenants
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': db_name,
        'USER': db_user,
        'PASSWORD': db_url.password or DB_PASSWORD,
        'HOST': db_host,
        'PORT': db_port,
        'OPTIONS': {
            'sslmode': DB_SSL_MODE,
            'connect_timeout': 10,
        },
        # Reuse database connections across requests (connection pooling) to
        # avoid the overhead of opening a new connection per request.
        'CONN_MAX_AGE': config('CONN_MAX_AGE', default=60, cast=int),
    }
}

# Display active database information
logger = logging.getLogger(__name__)
logger.info(f"""
╔═══════════════════════════════════════════════════════════╗
║  🗄️  ACTIVE DATABASE CONFIGURATION                       ║
╠═══════════════════════════════════════════════════════════╣
║  Mode:     {DATABASE_MODE.upper()}                                 ║
║  Type:     {active_db['label']}                          ║
║  Database: {db_name}                                     ║
║  Host:     {db_host}                                     ║
║  Port:     {db_port}                                     ║
║  SSL:      {DB_SSL_MODE}                                 ║
║  User:     {db_user}                                     ║
╚═══════════════════════════════════════════════════════════╝
""")

# ============================================
# CUSTOM USER MODEL
# ============================================
AUTH_USER_MODEL = 'users.GlobalUser'

# ============================================
# AUTHENTICATION BACKENDS
# ============================================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ============================================
# PASSWORD VALIDATION
# ============================================
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

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# ============================================
# STATIC & MEDIA FILES
# ============================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage' if DEBUG else 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# CORS SETTINGS
# ============================================
# Never allow ALL origins. Always use an explicit allowlist.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config(
        'CORS_ALLOWED_ORIGINS',
        default='http://localhost:5173,http://127.0.0.1:5173,http://admin.localhost:5173,http://localhost:9090,http://127.0.0.1:9090'
    ).split(',')
    if origin.strip()
]

# Tighten allowed headers — never use ['*'] with credentials enabled.
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'x-tenant-id',
    'x-correlation-id',
    'x-csrf-token',
    'origin',
    'x-subdomain',
    'x-admin-access',
]
CORS_PREFLIGHT_MAX_AGE = 86400
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT'
)

# ============================================
# CSRF SETTINGS
# ============================================
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config(
        'CSRF_TRUSTED_ORIGINS',
        default='http://localhost:5173,http://127.0.0.1:5173,http://admin.localhost:5173,http://localhost:9090,http://127.0.0.1:9090'
    ).split(',')
    if origin.strip()
]
CSRF_COOKIE_SECURE = not DEBUG
# Use Lax by default; Only relax to None when an explicit env override is set
# (required only for cross-site frontends, e.g. separate subdomain deployments).
CSRF_COOKIE_SAMESITE = config('CSRF_COOKIE_SAMESITE', default='Lax')
# Default HttpOnly=True for defense-in-depth against XSS cookie theft.
# Frontends must NOT read the CSRF cookie from JS (DRF frontends use JWT/session header).
CSRF_COOKIE_HTTPONLY = config('CSRF_COOKIE_HTTPONLY', default=True, cast=bool)

# ============================================
# REST FRAMEWORK SETTINGS
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.CookieJWTAuthentication',
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
    # Enable throttling by default (rates configurable via env).
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
        'smartcare_hms.throttling.UserAPIThrottle',
        'smartcare_hms.throttling.AnonymousUserThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'api': config('API_THROTTLE_RATE', default='1000/hour'),
        'anon': config('ANON_THROTTLE_RATE', default='25/hour'),
        'auth': config('AUTH_THROTTLE_RATE', default='5/min'),
        'password_reset': config('PASSWORD_RESET_THROTTLE_RATE', default='3/hour'),
        'password_reset_confirm': config('PASSWORD_RESET_CONFIRM_THROTTLE_RATE', default='5/hour'),
        'login_attempt': config('LOGIN_ATTEMPT_THROTTLE_RATE', default='5/15min'),
        '2fa': config('TWO_FA_THROTTLE_RATE', default='5/15min'),
        'audit': config('AUDIT_THROTTLE_RATE', default='1000/hour'),
    }
}

# ============================================
# JWT SETTINGS
# ============================================
# Use a dedicated signing key distinct from Django's SECRET_KEY.
# In production, fail fast if it is left as an insecure default.
_JWT_SIGNING_KEY = config('JWT_SIGNING_KEY', default=SECRET_KEY)
if (not DEBUG) and (_JWT_SIGNING_KEY in {
    'django-insecure-change-this-in-production',
    'changeme',
    'secret',
    'password',
} or _JWT_SIGNING_KEY == SECRET_KEY):
    raise RuntimeError(
        '🚨 JWT_SIGNING_KEY is insecure or missing. Set a strong, distinct '
        'JWT_SIGNING_KEY in production before starting the server.'
    )
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': _JWT_SIGNING_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ============================================
# CACHE SETTINGS - Redis-backed for shared cache across workers
# ============================================
# Redis is REQUIRED in production so that throttle counters, sessions, and
# cached data are consistent across all Gunicorn workers. In local development
# a locmem cache is acceptable, but we fail fast in production if REDIS_URL is
# missing to avoid silently degrading to per-worker/per-process state.
_REDIS_URL = config('REDIS_URL', default='')
if (not DEBUG) and not _REDIS_URL:
    raise RuntimeError(
        '🚨 REDIS_URL is required in production for consistent rate limiting, '
        'sessions, and caching. Set REDIS_URL before starting the server.'
    )
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': 'smartcare_hms',
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# ============================================
# SESSION SETTINGS
# ============================================
# Use Redis/cache-backed sessions when available to avoid a DB round-trip per
# request and to share sessions across workers.
if _REDIS_URL:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ============================================
# SECURITY SETTINGS
# ============================================
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default='false', cast=bool)

# Trusted proxy configuration: the app MUST sit behind a reverse proxy that
# terminates TLS and sets HTTPS on the request. This prevents rate-limit and
# scheme bypass via spoofed X-Forwarded-For / X-Forwarded-Proto headers.
# Default to a num-proxies of 1 (a single trusted proxy). In production set
# this to the actual proxy chain length.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = config('USE_X_FORWARDED_HOST', default=True, cast=bool)
SECURE_PROXY_SSL_HEADER_NUM_PROXIES = config('PROXY_COUNT', default=1, cast=int)

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'smartcare_hms.admin_security.AdminIPRestrictMiddleware',
    'smartcare_hms.throttling.RateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_tenants.middleware.main.TenantMainMiddleware',
    'tenants.middleware.HeaderTenantMiddleware',
    'csp.middleware.CSPMiddleware',
    'smartcare_hms.logging_middleware.CorrelationIdMiddleware',
    'smartcare_hms.logging_middleware.EnrichLoggingContextMiddleware',
    'smartcare_hms.logging_middleware.RequestResponseLoggingMiddleware',
]

CSP_DEFAULT_SRC = ["'self'"]
CSP_SCRIPT_SRC = ["'self'", "'unsafe-inline'"]
CSP_STYLE_SRC = ["'self'", "'unsafe-inline'"]
CSP_IMG_SRC = ["'self'", 'data:']
CSP_FONT_SRC = ["'self'"]
CSP_CONNECT_SRC = ["'self'"]
CSP_FRAME_ANCESTORS = ["'none'"]
CSP_FORM_ACTION = ["'self'"]
CSP_INCLUDE_NONCE_IN = ['script-src', 'style-src']

# ============================================
# ADMIN HARDENING
# ============================================
# Optional IP allowlist for the Django admin site. When set to a non-empty
# comma-separated list, requests to /admin/ are rejected unless the client IP
# (honouring X-Forwarded-For behind a trusted proxy) is in the allowlist.
# Leave empty to allow admin access from any IP (not recommended in prod).
ADMIN_ALLOWED_IPS = [
    ip.strip() for ip in config('ADMIN_ALLOWED_IPS', default='').split(',') if ip.strip()
]

# ============================================
# EMAIL SETTINGS
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@smartcarehms.local')
SERVER_EMAIL = config('SERVER_EMAIL', default='noreply@smartcarehms.local')

# ============================================
# CELERY SETTINGS
# ============================================
CELERY_TASK_ALWAYS_EAGER = False
if DEBUG:
    CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='memory://')
else:
    CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')

# Use Redis for the result backend when available to reduce DB writes; fall back
# to django-db only if explicitly configured (or in dev).
CELERY_RESULT_BACKEND = config(
    'CELERY_RESULT_BACKEND',
    default=(_REDIS_URL if _REDIS_URL else 'django-db'),
)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ============================================
# ENCRYPTION
# ============================================
# Require a strong encryption key. Insecure placeholders are rejected at boot
# so encrypted fields (2FA secrets, backup codes, RSA private keys) are never
# left trivially reversible in a production deployment.
ENCRYPTION_KEY = config('ENCRYPTION_KEY', default='your-32-char-key-for-encryption-change-this')
_INSECURE_KEYS = {
    'your-32-char-key-for-encryption-change-this',
    'changeme',
    'default-encryption-key-32-chars-long-here',
    'default',
}
if (not DEBUG) and (ENCRYPTION_KEY in _INSECURE_KEYS or '/' in ENCRYPTION_KEY or len(ENCRYPTION_KEY) < 32):
    raise RuntimeError(
        '🚨 ENCRYPTION_KEY is missing, weak, or insecure. Set a strong, random '
        'ENCRYPTION_KEY of at least 32 characters in production before storing '
        'sensitive data. Refusing to boot with an insecure encryption key.'
    )

# ============================================
# SWAGGER SETTINGS
# ============================================
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

# ============================================
# LOGGING
# ============================================
LOGGING_CONFIG = None
setup_logging(BASE_DIR, debug=DEBUG)

# ============================================
# FILE UPLOAD SETTINGS
# ============================================
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760

# ============================================
# APPLICATION-SPECIFIC SETTINGS
# ============================================
MAX_PATIENTS_PER_TENANT = 10000
MAX_USERS_PER_TENANT = 100

# ============================================
# FRONTEND URL
# ============================================
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# ============================================
# INTEGRATION KEYS
# ============================================
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')
FLUTTERWAVE_SECRET_KEY = config('FLUTTERWAVE_SECRET_KEY', default='')
SMS_API_KEY = config('SMS_API_KEY', default='')

# ============================================
# DIRECTORY CREATION
# ============================================
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
MEDIA_ROOT.mkdir(exist_ok=True)

# ============================================
# STORAGE BACKEND
# ============================================
from .storage import *  # noqa: E402,F403

# ============================================
# MULTI-TENANCY SETTINGS
# ============================================
TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.TenantDomain"
PUBLIC_SCHEMA_NAME = 'public'
PUBLIC_SCHEMA_URLCONF = 'smartcare_hms.urls_public'
TENANT_SCHEMA_URLCONF = 'smartcare_hms.urls'

# ============================================
# PRINT DATABASE CONFIGURATION (For verification)
# ============================================
print(f"""
╔═══════════════════════════════════════════════════════════╗
║  🚀 SMARTCARE HMS - STARTUP COMPLETE                     ║
╠═══════════════════════════════════════════════════════════╣
║  Debug Mode:     {DEBUG}                                 ║
║  Database Mode:  {DATABASE_MODE.upper()}                 ║
║  Database:       {db_name}                               ║
║  Host:           {db_host}:{db_port}                     ║
║  SSL:            {DB_SSL_MODE}                           ║
║  Frontend URL:   {FRONTEND_URL}                          ║
╚═══════════════════════════════════════════════════════════╝
""")