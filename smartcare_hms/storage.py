from decouple import config
from pathlib import Path

# Match BASE_DIR used in settings.py (project root, not the smartcare_hms app folder)
BASE_DIR = Path(__file__).resolve().parent.parent

# Storage backend configuration
# Priority: Supabase > S3 > Local filesystem
# Set USE_SUPABASE_STORAGE=True to use Supabase storage (S3-compatible).
# Set USE_S3=True to use AWS S3 storage.
# Otherwise local filesystem is used.

USE_S3 = config('USE_S3', default=False, cast=bool)
USE_SUPABASE_STORAGE = config('USE_SUPABASE_STORAGE', default=False, cast=bool)

if USE_S3:
    INSTALLED_APPS += ['storages']
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com' if AWS_STORAGE_BUCKET_NAME else ''
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/' if AWS_S3_CUSTOM_DOMAIN else '/media/'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

elif USE_SUPABASE_STORAGE:
    INSTALLED_APPS += ['storages']
    SUPABASE_PROJECT_ID = config('SUPABASE_PROJECT_ID', default='')
    SUPABASE_SERVICE_ROLE_KEY = config('SUPABASE_SERVICE_ROLE_KEY', default='')
    SUPABASE_S3_REGION = config('SUPABASE_S3_REGION', default='')

    if SUPABASE_PROJECT_ID:
        AWS_ACCESS_KEY_ID = 'service_role'
        AWS_SECRET_ACCESS_KEY = SUPABASE_SERVICE_ROLE_KEY
        AWS_STORAGE_BUCKET_NAME = SUPABASE_PROJECT_ID
        AWS_S3_REGION_NAME = SUPABASE_S3_REGION or 'us-east-1'
        AWS_S3_ENDPOINT_URL = f'https://{SUPABASE_PROJECT_ID}.storage.supabase.co/storage/v1/s3'
        AWS_S3_CUSTOM_DOMAIN = f'{SUPABASE_PROJECT_ID}.storage.supabase.co/storage/v1/object/public'
        AWS_S3_FILE_OVERWRITE = False
        AWS_DEFAULT_ACL = None
        AWS_QUERYSTRING_AUTH = True
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
        DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    else:
        MEDIA_URL = '/media/'
        MEDIA_ROOT = BASE_DIR / 'media'
        DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
