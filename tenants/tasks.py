import logging
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Q
from django.template.loader import render_to_string
from django.conf import settings
from celery import shared_task

from tenants.models import Tenant, SubscriptionExpiryNotification

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_subscription_expiry_notifications(self):
    """
    Daily task to check tenants with expiring subscriptions and send
    notification emails at 1 month, 2 weeks, 3 days, and on expiry date.
    """
    try:
        today = timezone.now().date()
        notification_windows = [
            (30, SubscriptionExpiryNotification.NotificationType.ONE_MONTH),
            (14, SubscriptionExpiryNotification.NotificationType.TWO_WEEKS),
            (3, SubscriptionExpiryNotification.NotificationType.THREE_DAYS),
            (0, SubscriptionExpiryNotification.NotificationType.DEADLINE),
        ]

        active_tenants = Tenant.objects.filter(
            subscription_status__in=['active', 'trial'],
            subscription_end_date__isnull=False,
            subscription_end_date__gte=today - timedelta(days=1),
            subscription_end_date__lte=today + timedelta(days=30),
        ).select_related('subscription_plan').only(
            'id', 'name', 'email', 'subscription_end_date',
            'subscription_status', 'subscription_plan_id'
        )

        sent_count = 0
        skipped_count = 0

        for tenant in active_tenants:
            days_remaining = (tenant.subscription_end_date - today).days

            for threshold, notification_type in notification_windows:
                if days_remaining == threshold:
                    already_sent = SubscriptionExpiryNotification.objects.filter(
                        tenant=tenant,
                        notification_type=notification_type,
                        is_sent=True
                    ).exists()

                    if already_sent:
                        skipped_count += 1
                        continue

                    try:
                        _send_expiry_email(tenant, days_remaining, notification_type)
                        SubscriptionExpiryNotification.objects.create(
                            tenant=tenant,
                            notification_type=notification_type,
                            recipient_email=tenant.billing_email or tenant.email,
                            subject=_get_subject(tenant, days_remaining, notification_type),
                            body=_get_body(tenant, days_remaining, notification_type),
                            is_sent=True,
                        )
                        sent_count += 1
                    except Exception as exc:
                        logger.error(f"Failed to send {notification_type} expiry email to {tenant.name}: {exc}")
                        SubscriptionExpiryNotification.objects.create(
                            tenant=tenant,
                            notification_type=notification_type,
                            recipient_email=tenant.billing_email or tenant.email,
                            subject=_get_subject(tenant, days_remaining, notification_type),
                            body=_get_body(tenant, days_remaining, notification_type),
                            is_sent=False,
                        )
                        raise self.retry(exc=exc)

        logger.info(f"Subscription expiry notification task completed: {sent_count} sent, {skipped_count} skipped")
        return {
            'sent': sent_count,
            'skipped': skipped_count,
            'processed': sent_count + skipped_count,
        }

    except Exception as exc:
        logger.error(f"Subscription expiry notification task failed: {exc}")
        raise self.retry(exc=exc)


def _get_subject(tenant, days_remaining, notification_type):
    if notification_type == SubscriptionExpiryNotification.NotificationType.DEADLINE:
        return f"URGENT: {tenant.name} subscription expires today"
    return f"{tenant.name}: {days_remaining} days left in subscription"


def _get_body(tenant, days_remaining, notification_type):
    plan_name = tenant.subscription_plan.name if tenant.subscription_plan else 'your plan'
    return (
        f"Dear {tenant.name} Admin,\n\n"
        f"Your subscription to {plan_name} expires in {days_remaining} day(s). "
        f"Subscription end date: {tenant.subscription_end_date}.\n\n"
        f"Please renew your subscription to avoid service interruption.\n\n"
        f"Best regards,\n{settings.APP_NAME} Team"
    )


def _send_expiry_email(tenant, days_remaining, notification_type):
    plan_name = tenant.subscription_plan.name if tenant.subscription_plan else 'your plan'
    subject = _get_subject(tenant, days_remaining, notification_type)

    context = {
        'tenant_name': tenant.name,
        'plan_name': plan_name,
        'days_remaining': days_remaining,
        'subscription_end_date': tenant.subscription_end_date,
        'subscription_status': tenant.subscription_status,
        'app_name': settings.APP_NAME,
        'support_email': settings.DEFAULT_FROM_EMAIL,
    }

    try:
        from tenants.communication import build_email_context, send_tenant_email
        context = build_email_context(tenant, extra=context)
        subject = f"{tenant.name} - Subscription Expiry Notice"
    except Exception:
        from tenants.communication import send_tenant_email

    html_message = render_to_string('emails/subscription_expiry.html', context)
    plain_message = render_to_string('emails/subscription_expiry.txt', context)

    send_tenant_email(
        tenant=tenant,
        subject=subject,
        message=plain_message,
        recipient_list=[tenant.billing_email or tenant.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_staff_welcome_email(recipient_email, staff_name, tenant_id, employee_id, temporary_password, login_url):
    """Send newly created tenant staff their first-login credentials using tenant email configuration."""
    import datetime
    from tenants.models import Tenant
    from tenants.communication import build_email_context, send_tenant_email

    tenant = Tenant.objects.get(pk=tenant_id)
    subject = f'Welcome to {tenant.name} - Your Staff Account'
    base_context = {
        'staff_name': staff_name,
        'tenant_name': tenant.name,
        'employee_id': employee_id,
        'recipient_email': recipient_email,
        'temporary_password': temporary_password,
        'login_url': login_url,
        'app_name': settings.APP_NAME,
        'year': datetime.date.today().year,
    }
    context = build_email_context(tenant, extra=base_context)

    send_tenant_email(
        tenant=tenant,
        subject=subject,
        message=render_to_string('users/staff_welcome_email.txt', context),
        recipient_list=[recipient_email],
        html_message=render_to_string('users/staff_welcome_email.html', context),
        fail_silently=False,
    )
    return {'status': 'success', 'email': recipient_email}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_staff_welcome_email_task(self, recipient_email, staff_name, tenant_id, employee_id, temporary_password, login_url):
    try:
        return send_staff_welcome_email(
            recipient_email, staff_name, tenant_id, employee_id, temporary_password, login_url
        )
    except Exception as exc:
        logger.exception('Failed to send staff welcome email to %s', recipient_email)
        raise self.retry(exc=exc)
