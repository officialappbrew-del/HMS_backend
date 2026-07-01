import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_task(self, recipient_email, reset_token, user_name=None):
    """
    Send password reset email in background.
    Retries up to 3 times with 60 seconds delay between retries.
    """
    try:
        from django.conf import settings
        import os
        
        logger.info(f'🚀 Starting password reset email task for {recipient_email}')
        logger.info(f'   Email Backend: {settings.EMAIL_BACKEND}')
        logger.info(f'   DEBUG Mode: {settings.DEBUG}')
        
        subject = 'SmartCare HMS - Password Reset Request'
        
        context = {
            'user_name': user_name or 'User',
            'reset_token': reset_token,
            'reset_url': f'{settings.FRONTEND_URL}/reset-password?token={reset_token}' if hasattr(settings, 'FRONTEND_URL') else None,
            'expiry_hours': 1,
        }
        
        html_message = render_to_string('users/password_reset_email.html', context)
        plain_message = render_to_string('users/password_reset_email.txt', context)
        
        logger.info(f'   Subject: {subject}')
        logger.info(f'   To: {recipient_email}')
        logger.info(f'   From: {settings.DEFAULT_FROM_EMAIL}')
        
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
