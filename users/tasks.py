import logging
import threading
from urllib.parse import quote
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings
from smartcare_hms.email_delivery import is_async_email_delivery

logger = logging.getLogger(__name__)


def dispatch_email_task(task, args=(), kwargs=None):
    from smartcare_hms.email_delivery import dispatch_email_task as dispatch
    return dispatch(task, args=args, kwargs=kwargs)


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
    Uses per-tenant email identity when available, falls back to global settings.
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
            'reset_url': f'{settings.FRONTEND_URL.rstrip("/")}/login?token={quote(reset_token)}' if hasattr(settings, 'FRONTEND_URL') else None,
            'expiry_hours': 1,
            'app_name': settings.APP_NAME,
        }

        tenant = _resolve_tenant_from_context(recipient_email, user_name)
        html_message = render_to_string('users/password_reset_email.html', base_context)
        plain_message = render_to_string('users/password_reset_email.txt', base_context)

        logger.info(f'   Subject: {subject}')
        logger.info(f'   To: {recipient_email}')

        if tenant:
            # Use tenant-specific email configuration when tenant is available
            try:
                from tenants.communication import build_email_context, send_tenant_email
                context = build_email_context(tenant, extra=base_context)
                html_message = render_to_string('users/password_reset_email.html', context)
                plain_message = render_to_string('users/password_reset_email.txt', context)
                subject = f'{tenant.name} - Password Reset Request'
                logger.info(f'   Using tenant email configuration for {tenant.name}')
                result = send_tenant_email(
                    tenant=tenant,
                    subject=subject,
                    message=plain_message,
                    recipient_list=[recipient_email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as exc:
                logger.warning(f'   Failed to use tenant configuration, falling back to global settings: {exc}')
                # Fall through to global send_mail below
                result = send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_email],
                    html_message=html_message,
                    fail_silently=False,
                )
        else:
            # No tenant context; use global settings
            logger.info(f'   No tenant found, using global email settings')
            result = send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
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
def send_login_notification_email_task(
    self,
    recipient_email,
    user_name=None,
    tenant_id=None,
    ip_address=None,
    user_agent=None,
    is_global_user=False,
):
    """Notify an account owner about a successful login without blocking auth."""
    if not recipient_email:
        return {'status': 'skipped', 'reason': 'missing email'}

    try:
        from tenants.communication import build_email_context, send_tenant_email
        from tenants.models import Tenant

        tenant = None
        if tenant_id:
            tenant = Tenant.objects.filter(public_id=tenant_id).first()
            if tenant is None and str(tenant_id).isdigit():
                tenant = Tenant.objects.filter(id=int(tenant_id)).first()

        base_context = {
            'user_name': user_name or 'User',
            'login_time': timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M %Z'),
            'ip_address': ip_address or 'Unavailable',
            'device': (user_agent or 'Unknown device')[:500],
            'app_name': settings.APP_NAME,
            'tenant_name': getattr(tenant, 'name', None) or '',
        }

        if is_global_user:
            send_mail(
                subject='New Sign-in to Your Account',
                message=render_to_string('users/login_notification_email.txt', base_context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=render_to_string('users/login_notification_email.html', base_context),
                fail_silently=False,
            )
            logger.info('Login notification email sent to %s using global credentials', recipient_email)
            return {'status': 'success', 'email': recipient_email, 'tenant': 'global'}

        if tenant:
            context = build_email_context(tenant, extra=base_context)
            subject = f'{tenant.name} - New Sign-in to Your Account'
            try:
                send_tenant_email(
                    tenant=tenant,
                    subject=subject,
                    message=render_to_string('users/login_notification_email.txt', context),
                    recipient_list=[recipient_email],
                    html_message=render_to_string('users/login_notification_email.html', context),
                    fail_silently=False,
                )
            except Exception:
                logger.warning(
                    'Login notification skipped for tenant %s because tenant email credentials are not configured or delivery failed.',
                    tenant.name,
                    exc_info=True,
                )
                return {'status': 'skipped', 'email': recipient_email, 'reason': 'tenant_email_not_configured'}
            logger.info('Login notification email sent to %s using tenant credentials for %s', recipient_email, tenant.name)
            return {'status': 'success', 'email': recipient_email, 'tenant': tenant.name}

        logger.warning('Login notification skipped: no tenant context for %s; tenant-scoped notification only.', recipient_email)
        return {'status': 'skipped', 'email': recipient_email, 'reason': 'no_tenant_context'}
    except Exception as exc:
        logger.exception('Failed to send login notification email to %s', recipient_email)
        raise self.retry(exc=exc)


def _queue_login_notification_async(recipient_email, user_name=None, tenant_id=None,
                                   ip_address=None, user_agent=None, is_global_user=False):
    """Best-effort worker-thread enqueue; avoids blocking the login response."""
    try:
        send_login_notification_email_task.apply_async(
            kwargs={
                'recipient_email': recipient_email,
                'user_name': user_name,
                'tenant_id': str(tenant_id) if tenant_id else None,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'is_global_user': is_global_user,
            },
            ignore_result=True,
        )
    except Exception as exc:
        logger.warning(
            'Login notification email was not queued for %s because the Celery broker is unavailable: %s',
            recipient_email,
            exc,
        )


def queue_login_notification(recipient_email, user_name=None, tenant_id=None,
                             ip_address=None, user_agent=None, is_global_user=False):
    """Dispatch a login notification according to EMAIL_DELIVERY_MODE."""
    if not recipient_email:
        return

    if not is_async_email_delivery():
        try:
            send_login_notification_email_task.run(
                recipient_email=recipient_email,
                user_name=user_name,
                tenant_id=str(tenant_id) if tenant_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                is_global_user=is_global_user,
            )
        except Exception as exc:
            logger.warning('Login notification email failed in sync mode for %s: %s', recipient_email, exc)
        return

    thread = threading.Thread(
        target=_queue_login_notification_async,
        args=(recipient_email,),
        kwargs={
            'user_name': user_name,
            'tenant_id': tenant_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'is_global_user': is_global_user,
        },
        daemon=True,
    )
    thread.start()


def send_tenant_welcome_email(recipient_email, admin_name, tenant_name, temporary_password, login_url, user_id=None):
    """Send tenant welcome email with first-login credentials using tenant email configuration."""
    import datetime
    from tenants.models import TenantUser
    from tenants.communication import send_tenant_email

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
    
    tenant_instance = None
    if user_id:
        tenant_user = TenantUser.objects.select_related('tenant').filter(employee_id=user_id).first()
        if not tenant_user and str(user_id).isdigit():
            tenant_user = TenantUser.objects.select_related('tenant').filter(id=user_id).first()
        if tenant_user:
            tenant_instance = tenant_user.tenant_id
        if tenant_instance:
            from tenants.models import Tenant
            tenant_instance = Tenant.objects.get(pk=tenant_instance)

    if tenant_instance:
        from tenants.communication import build_email_context
        context = build_email_context(tenant_instance, extra=base_context)
        subject = f'Welcome to {tenant_instance.name} - Account Created'
        result = send_tenant_email(
            tenant=tenant_instance,
            subject=subject,
            message=render_to_string('users/staff_account_created_email.txt', context),
            recipient_list=[recipient_email],
            html_message=render_to_string('users/staff_account_created_email.html', context),
            fail_silently=False,
            allow_global_fallback=False,
        )
    else:
        # Fall back to global settings if tenant not available
        context = dict(base_context)
        result = send_mail(
            subject=subject,
            message=render_to_string('users/tenant_welcome_email.txt', context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=render_to_string('users/tenant_welcome_email.html', context),
            fail_silently=False,
        )
    
    return {'status': 'success', 'email': recipient_email, 'messages_sent': result}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_tenant_welcome_email_task(self, recipient_email, admin_name, tenant_name, temporary_password, login_url, user_id=None):
    try:
        return send_tenant_welcome_email(
            recipient_email, admin_name, tenant_name, temporary_password, login_url, user_id
        )
    except Exception as exc:
        logger.error(f'Failed to send tenant welcome email to {recipient_email}')
        logger.exception(f'Error: {exc}')
        raise self.retry(exc=exc)
