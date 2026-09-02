"""Email delivery mode selection for application email workflows."""

from django.conf import settings


def is_async_email_delivery():
    """Return whether application emails should be queued through Celery."""
    return getattr(settings, 'EMAIL_DELIVERY_MODE', 'async') == 'async'


def dispatch_email_task(task, args=(), kwargs=None):
    """Run an email task asynchronously or synchronously based on configuration."""
    if is_async_email_delivery():
        return task.delay(*args, **(kwargs or {}))
    return task.run(*args, **(kwargs or {}))
