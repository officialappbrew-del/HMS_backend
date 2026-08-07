"""
Per-tenant communication identity routing service.

Resolves the correct sender identity (email/SMS) for a given tenant
at send-time, so outbound messages use the hospital's own verified
sender identity rather than a global shared one.
"""


def get_communication_profile(tenant):
    """Return the CommunicationProfile for a tenant, creating a default one if missing."""
    from .models import CommunicationProfile

    profile = getattr(tenant, 'communication_profile', None)
    if profile:
        return profile
    return CommunicationProfile.objects.create(tenant=tenant)


def resolve_email_identity(tenant):
    """Resolve email sending identity for a tenant.

    Returns a dict with keys:
      from_email, from_name, reply_to, host, port, username, password, use_tls, provider

    Falls back to global Django settings when the tenant has no profile or values.
    """
    from django.conf import settings as django_settings

    profile = get_communication_profile(tenant)

    return {
        'from_email': profile.email_from or getattr(django_settings, 'DEFAULT_FROM_EMAIL', ''),
        'from_name': profile.from_name or tenant.name,
        'reply_to': profile.reply_to or profile.email_from or getattr(django_settings, 'DEFAULT_FROM_EMAIL', ''),
        'host': profile.email_host or getattr(django_settings, 'EMAIL_HOST', ''),
        'port': profile.email_port or getattr(django_settings, 'EMAIL_PORT', 587),
        'username': profile.email_username or getattr(django_settings, 'EMAIL_HOST_USER', ''),
        'password': profile.get_decrypted_email_password() or getattr(django_settings, 'EMAIL_HOST_PASSWORD', ''),
        'use_tls': profile.email_use_tls if profile.email_host else getattr(django_settings, 'EMAIL_USE_TLS', True),
        'provider': profile.email_provider or 'default',
        'verified_domain': profile.verified_domain or '',
    }


def resolve_sms_identity(tenant):
    """Resolve SMS sending identity for a tenant.

    Returns a dict with keys:
      provider, sender_id, phone_number, api_key, country_code

    Falls back to global settings when the tenant has no profile or values.
    """
    from django.conf import settings as django_settings

    profile = get_communication_profile(tenant)

    return {
        'provider': profile.sms_provider or 'default',
        'sender_id': profile.sms_sender_id or tenant.name,
        'phone_number': profile.sms_phone_number or getattr(django_settings, 'SMS_PHONE_NUMBER', ''),
        'api_key': profile.get_decrypted_sms_api_key() or getattr(django_settings, 'SMS_API_KEY', ''),
        'country_code': profile.sms_country_code or 'NG',
    }


def is_email_enabled(tenant):
    profile = get_communication_profile(tenant)
    return bool(profile.email_enabled)


def is_sms_enabled(tenant):
    profile = get_communication_profile(tenant)
    return bool(profile.sms_enabled)


def get_message_template(tenant, channel, message_type):
    """Return a pre-approved message template for a tenant/channel/type, or None."""
    profile = get_communication_profile(tenant)
    templates = profile.message_templates or {}
    if not isinstance(templates, dict):
        return None
    channel_templates = templates.get(channel, {})
    return channel_templates.get(message_type)


def get_tenant_logo_url(tenant, request=None):
    """Return an absolute URL for the tenant's logo, or an empty string.

    Falls back to the request's media URL when no request is provided, and
    builds an absolute URI so the logo renders inside email clients.
    """
    logo = getattr(tenant, 'logo', None)
    if not logo:
        return ''

    try:
        if request is not None:
            return request.build_absolute_uri(logo.url)

        # Build an absolute URL from MEDIA_URL + MEDIA_ROOT when possible.
        from django.conf import settings as django_settings
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')

        if media_url.startswith('http://') or media_url.startswith('https://'):
            # Remote storage (S3/Supabase) already yields an absolute URL.
            return media_url.rstrip('/') + logo.url
        return ''  # Relative media; no host available in a background task.
    except Exception:
        return ''


def build_email_context(tenant, extra=None, request=None):
    """Build a template context carrying the tenant's brand for outbound emails.

    Returns a dict with:
      tenant_name, tenant_logo_url, year

    merged with any ``extra`` context provided by the caller.
    """
    import datetime

    context = {
        'tenant_name': getattr(tenant, 'name', None) or '',
        'tenant_logo_url': get_tenant_logo_url(tenant, request=request),
        'year': datetime.date.today().year,
    }
    if extra and isinstance(extra, dict):
        context.update(extra)
    return context

