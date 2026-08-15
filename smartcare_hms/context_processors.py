from django.conf import settings


def app_name(request):
    return {
        'app_name': getattr(settings, 'APP_NAME', 'SmartCare HMS'),
    }
