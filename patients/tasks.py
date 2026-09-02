import logging

from celery import shared_task
from django.conf import settings
from django.template.loader import render_to_string

from .models import Appointment
from tenants.communication import build_email_context, send_tenant_email

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_appointment_email_task(self, appointment_id, recipient_type='patient'):
    try:
        appointment = Appointment.objects.select_related('tenant', 'patient', 'doctor').get(pk=appointment_id)
        tenant = appointment.tenant
        if recipient_type == 'doctor':
            recipient = appointment.doctor
            recipient_email = getattr(recipient, 'email', '')
            subject = f'{tenant.name} - Appointment Assigned'
            text_template = 'patients/appointment_assigned_email.txt'
            html_template = 'patients/appointment_assigned_email.html'
            extra = {'doctor_name': recipient.get_full_name() if recipient else ''}
        else:
            recipient = appointment.patient
            recipient_email = getattr(recipient, 'email', '')
            subject = f'{tenant.name} - Appointment Confirmation'
            text_template = 'patients/appointment_reminder_email.txt'
            html_template = 'patients/appointment_reminder_email.html'
            extra = {'patient_name': recipient.get_full_name() if recipient else ''}

        if not recipient_email:
            return {'status': 'skipped', 'reason': 'missing recipient email'}

        context = build_email_context(tenant, extra={
            **extra,
            'app_name': getattr(settings, 'APP_NAME', 'SmartCare HMS'),
            'appointment_date': appointment.scheduled_date,
            'appointment_time': appointment.scheduled_time,
            'appointment_type': appointment.get_appointment_type_display(),
            'doctor_name': appointment.doctor.get_full_name() if appointment.doctor else '',
            'patient_name': appointment.patient.get_full_name(),
            'reason': appointment.reason,
        })
        send_tenant_email(
            tenant=tenant,
            subject=subject,
            message=render_to_string(text_template, context),
            recipient_list=[recipient_email],
            html_message=render_to_string(html_template, context),
            fail_silently=False,
            allow_global_fallback=False,
        )
        return {'status': 'success', 'email': recipient_email}
    except Exception as exc:
        logger.exception('Failed to send appointment email for %s', appointment_id)
        raise self.retry(exc=exc)
