import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


def _resolve_tenant_from_context(recipient_email, user_name=None):
    """Best-effort tenant resolution for background email tasks.

    Background tasks do not carry request user context, so we attempt
    to resolve the tenant from known user identifiers. If resolution
    fails, we fall back to global DEFAULT_FROM_EMAIL.
    """
    try:
        from tenants.models import TenantUser, Tenant
        tenant_user = TenantUser.objects.filter(email=recipient_email).first()
        if tenant_user:
            return tenant_user.tenant
        if user_name:
            tenant_user = TenantUser.objects.filter(
                first_name__iexact=user_name.split(' ')[0]
            ).first()
            if tenant_user:
                return tenant_user.tenant
    except Exception:
        pass
    return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_task(self, recipient_email, reset_token, user_name=None):
    """
    Send password reset email in background.
    Retries up to 3 times with 60 seconds delay between retries.
    Uses per-tenant email identity when available.
    """
    try:
        from django.conf import settings
        import os

        logger.info(f'🚀 Starting password reset email task for {recipient_email}')
        logger.info(f'   Email Backend: {settings.EMAIL_BACKEND}')
        logger.info(f'   DEBUG Mode: {settings.DEBUG}')

        subject = 'Password Reset Request'

        base_context = {
            'user_name': user_name or 'User',
            'reset_token': reset_token,
            'reset_url': f'{settings.FRONTEND_URL}/reset-password?token={reset_token}' if hasattr(settings, 'FRONTEND_URL') else None,
            'expiry_hours': 1,
            'app_name': settings.APP_NAME,
        }

        tenant = _resolve_tenant_from_context(recipient_email, user_name)
        from_email = settings.DEFAULT_FROM_EMAIL
        from_name = None

        # Merge per-tenant brand context (name + logo) so the email renders
        # with the hospital's branding, not the global brand.
        context = dict(base_context)
        if tenant:
            try:
                from tenants.communication import build_email_context, resolve_email_identity
                context = build_email_context(tenant, extra=base_context)
                identity = resolve_email_identity(tenant)
                from_email = identity['from_email'] or from_email
                from_name = identity['from_name'] or None
                if not from_name and tenant.name:
                    from_name = tenant.name
                subject = f'{tenant.name} - Password Reset Request'
            except Exception:
                pass

        html_message = render_to_string('users/password_reset_email.html', context)
        plain_message = render_to_string('users/password_reset_email.txt', context)

        if from_name:
            from_email = f'{from_name} <{from_email}>'

        logger.info(f'   Subject: {subject}')
        logger.info(f'   To: {recipient_email}')
        logger.info(f'   From: {from_email}')

        result = send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f'✅ Password reset email sent successfully to {recipient_email}')
        logger.info(f'   Send result: {result} message(s) sent')

        # If file backend, log where email was saved
        if 'filebased' in settings.EMAIL_BACKEND:
            email_file_path = settings.EMAIL_FILE_PATH if hasattr(settings, 'EMAIL_FILE_PATH') else os.path.join(settings.BASE_DIR, 'logs', 'emails')
            logger.info(f'   📁 Email file saved to: {email_file_path}')

        return {'status': 'success', 'email': recipient_email, 'messages_sent': result}

    except Exception as exc:
        logger.error(f'❌ Failed to send password reset email to {recipient_email}')
        logger.exception(f'   Error: {exc}')
        # Retry task
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_tenant_welcome_email_task(self, recipient_email, admin_name, tenant_name, temporary_password, login_url, user_id=None):
    """
    Send tenant welcome email with credentials in background.
    Retries up to 3 times with 60 seconds delay between retries.
    Uses per-tenant email identity when available.
    """
    try:
        from django.conf import settings
        import os
        import datetime

        logger.info(f'🚀 Starting tenant welcome email task for {recipient_email}')
        logger.info(f'   Email Backend: {settings.EMAIL_BACKEND}')
        logger.info(f'   DEBUG Mode: {settings.DEBUG}')

        subject = f'Welcome to {tenant_name} - Your Account Has Been Created'

        base_context = {
            'admin_name': admin_name,
            'tenant_name': tenant_name,
            'temporary_password': temporary_password,
            'login_url': login_url,
            'user_id': user_id or '',
            'admin_email': recipient_email,
            'year': datetime.date.today().year,
            'app_name': settings.APP_NAME,
        }

        tenant = None
        if user_id:
            try:
                from tenants.models import TenantUser, Tenant
                tenant_user = TenantUser.objects.filter(id=user_id).first()
                if tenant_user:
                    tenant = tenant_user.tenant
            except Exception:
                pass

        from_email = settings.DEFAULT_FROM_EMAIL
        from_name = None

        context = dict(base_context)
        if tenant:
            try:
                from tenants.communication import build_email_context, resolve_email_identity
                context = build_email_context(tenant, extra=base_context)
                identity = resolve_email_identity(tenant)
                from_email = identity['from_email'] or from_email
                from_name = identity['from_name'] or None
                if not from_name and tenant.name:
                    from_name = tenant.name
                subject = f'Welcome to {tenant.name} - Account Created'
            except Exception:
                pass

        html_message = render_to_string('users/tenant_welcome_email.html', context)
        plain_message = render_to_string('users/tenant_welcome_email.txt', context)

        if from_name:
            from_email = f'{from_name} <{from_email}>'

        logger.info(f'   Subject: {subject}')
        logger.info(f'   To: {recipient_email}')
        logger.info(f'   From: {from_email}')

        result = send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f'✅ Tenant welcome email sent successfully to {recipient_email}')
        logger.info(f'   Send result: {result} message(s) sent')

        if 'filebased' in settings.EMAIL_BACKEND:
            email_file_path = settings.EMAIL_FILE_PATH if hasattr(settings, 'EMAIL_FILE_PATH') else os.path.join(settings.BASE_DIR, 'logs', 'emails')
            logger.info(f'   📁 Email file saved to: {email_file_path}')

        return {'status': 'success', 'email': recipient_email, 'messages_sent': result}

    except Exception as exc:
        logger.error(f'❌ Failed to send tenant welcome email to {recipient_email}')
        logger.exception(f'   Error: {exc}')
        raise self.retry(exc=exc)
