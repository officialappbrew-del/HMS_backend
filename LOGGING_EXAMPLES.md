"""
LOGGING EXAMPLES FOR SmartCare HMS

This file demonstrates how to integrate the enterprise logging system
into your Django apps. Copy and adapt these patterns for your own code.
"""

# ============================================================================
# 1. VIEWS - HTTP Request Logging
# ============================================================================

from rest_framework.views import APIView
from rest_framework.response import Response
from smartcare_hms.logging_utils import logger, get_audit_logger, log_security_event
import json


class PatientCreateView(APIView):
    """
    Example: Patient creation with audit logging
    """
    def post(self, request):
        try:
            # Your creation logic here
            patient_data = request.data
            patient = Patient.objects.create(**patient_data)
            
            # Log audit event
            log_audit_event(
                action='CREATE',
                resource='Patient',
                resource_id=patient.id,
                user_id=request.user.id if request.user.is_authenticated else None,
                tenant_id=request.tenant.id if hasattr(request, 'tenant') else None,
                status='success',
                details={
                    'name': patient.name,
                    'email': patient.email,
                    'phone': patient.phone_number
                }
            )
            
            logger.info(
                'Patient created successfully',
                patient_id=patient.id,
                user_id=request.user.id,
                tenant_id=getattr(request, 'tenant', {}).id
            )
            
            return Response({'id': patient.id, 'name': patient.name}, status=201)
            
        except ValueError as e:
            logger.error(
                'Invalid patient data provided',
                exception=e,
                context={'user_id': request.user.id}
            )
            return Response({'error': 'Invalid data'}, status=400)
            
        except Exception as e:
            logger.error(
                'Unexpected error creating patient',
                exception=e,
                context={
                    'user_id': request.user.id,
                    'tenant_id': getattr(request, 'tenant', {}).id
                }
            )
            return Response({'error': 'Internal server error'}, status=500)


class UserLoginView(APIView):
    """
    Example: Login with security event logging
    """
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        try:
            from django.contrib.auth import authenticate
            user = authenticate(username=username, password=password)
            
            if user:
                # Successful login
                log_security_event(
                    event_type='LOGIN_SUCCESS',
                    user_id=user.id,
                    status='success',
                    ip_address=get_client_ip(request)
                )
                
                logger.info(
                    'User login successful',
                    user_id=user.id,
                    ip_address=get_client_ip(request)
                )
                
                token = generate_jwt_token(user)
                return Response({'token': token})
            else:
                # Failed login
                log_security_event(
                    event_type='LOGIN_FAILURE',
                    username=username,
                    status='failure',
                    ip_address=get_client_ip(request)
                )
                
                logger.warning(
                    'Login attempt failed',
                    username=username,
                    ip_address=get_client_ip(request)
                )
                
                return Response({'error': 'Invalid credentials'}, status=401)
                
        except Exception as e:
            logger.error(
                'Error during login',
                exception=e,
                context={'username': username}
            )
            return Response({'error': 'Login error'}, status=500)


# ============================================================================
# 2. MODELS - Save/Delete Logging
# ============================================================================

from django.db import models
from smartcare_hms.logging_utils import log_audit_event, LogExecutionTime


class Patient(models.Model):
    """
    Example: Patient model with audit logging on save/delete
    """
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_data = {}
        
        if not is_new:
            # Track what changed for audit log
            old_instance = Patient.objects.get(pk=self.pk)
            old_data = {
                'name': old_instance.name,
                'email': old_instance.email,
                'phone_number': old_instance.phone_number
            }
        
        super().save(*args, **kwargs)
        
        if is_new:
            log_audit_event(
                action='CREATE',
                resource='Patient',
                resource_id=self.pk,
                status='success',
                details={
                    'name': self.name,
                    'email': self.email,
                    'phone_number': self.phone_number
                }
            )
        else:
            # Log only changes
            changes = {}
            if old_data['name'] != self.name:
                changes['name'] = {'old': old_data['name'], 'new': self.name}
            if old_data['email'] != self.email:
                changes['email'] = {'old': old_data['email'], 'new': self.email}
            if old_data['phone_number'] != self.phone_number:
                changes['phone_number'] = {'old': old_data['phone_number'], 'new': self.phone_number}
            
            if changes:
                log_audit_event(
                    action='UPDATE',
                    resource='Patient',
                    resource_id=self.pk,
                    status='success',
                    details=changes
                )
    
    def delete(self, *args, **kwargs):
        patient_id = self.pk
        super().delete(*args, **kwargs)
        
        log_audit_event(
            action='DELETE',
            resource='Patient',
            resource_id=patient_id,
            status='success',
            details={'name': self.name}
        )


class Appointment(models.Model):
    """
    Example: With performance logging
    """
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey('Doctor', on_delete=models.CASCADE)
    scheduled_at = models.DateTimeField()
    
    def send_reminder(self):
        """Send appointment reminder with performance logging"""
        with LogExecutionTime('send_appointment_reminder'):
            # Your reminder sending logic
            sms_result = send_sms(self.patient.phone_number, 
                                 f'Reminder: Appointment at {self.scheduled_at}')
            
            logger.info(
                'Appointment reminder sent',
                appointment_id=self.id,
                patient_id=self.patient.id,
                sms_sent=sms_result
            )


# ============================================================================
# 3. SERIALIZERS - Data Validation Logging
# ============================================================================

from rest_framework import serializers


class PatientSerializer(serializers.ModelSerializer):
    """
    Example: Serializer with validation logging
    """
    class Meta:
        model = Patient
        fields = ['id', 'name', 'email', 'phone_number']
    
    def validate_email(self, value):
        """Validate email and log if invalid"""
        if Patient.objects.filter(email=value).exists():
            logger.warning(
                'Duplicate email attempted',
                email=value,
                resource='Patient'
            )
            raise serializers.ValidationError("Email already registered")
        return value
    
    def create(self, validated_data):
        """Create with logging"""
        patient = Patient.objects.create(**validated_data)
        logger.info(
            'Patient serializer created',
            patient_id=patient.id
        )
        return patient


# ============================================================================
# 4. SIGNAL HANDLERS - Event Logging
# ============================================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=Patient)
def log_patient_change(sender, instance, created, **kwargs):
    """
    Signal handler to log patient changes
    """
    if created:
        logger.info(
            'Patient signal: Created',
            patient_id=instance.id,
            name=instance.name
        )
    else:
        logger.debug(
            'Patient signal: Updated',
            patient_id=instance.id
        )


@receiver(post_delete, sender=Patient)
def log_patient_delete(sender, instance, **kwargs):
    """
    Signal handler to log patient deletion
    """
    logger.warning(
        'Patient signal: Deleted',
        patient_id=instance.id,
        name=instance.name
    )


# ============================================================================
# 5. CELERY TASKS - Async Task Logging
# ============================================================================

from celery import shared_task
from smartcare_hms.logging_utils import log_task_execution
import time


@shared_task
def send_daily_reminders():
    """
    Example: Celery task with execution logging
    """
    start_time = time.time()
    
    try:
        # Get appointments for today
        today_appointments = Appointment.objects.filter(
            scheduled_at__date=timezone.now().date()
        )
        
        sent_count = 0
        for appointment in today_appointments:
            appointment.send_reminder()
            sent_count += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        log_task_execution(
            task_name='send_daily_reminders',
            status='completed',
            duration_ms=duration_ms,
            result={
                'total_appointments': today_appointments.count(),
                'reminders_sent': sent_count
            }
        )
        
        logger.info(
            'Daily reminders completed',
            total=today_appointments.count(),
            sent=sent_count,
            duration_ms=round(duration_ms, 2)
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        
        log_task_execution(
            task_name='send_daily_reminders',
            status='failed',
            duration_ms=duration_ms,
            error=str(e)
        )
        
        logger.error(
            'Daily reminders task failed',
            exception=e,
            duration_ms=round(duration_ms, 2)
        )
        raise


# ============================================================================
# 6. PERMISSIONS & SECURITY - Permission Logging
# ============================================================================

from rest_framework.permissions import BasePermission
from smartcare_hms.logging_utils import log_security_event


class IsPatientOwnerOrDoctor(BasePermission):
    """
    Example: Permission class with logging
    """
    message = 'You do not have permission to access this resource.'
    
    def has_object_permission(self, request, view, obj):
        # Check permission
        is_allowed = (
            request.user == obj.patient.user or 
            request.user.groups.filter(name='Doctor').exists()
        )
        
        if not is_allowed:
            log_security_event(
                event_type='PERMISSION_DENIED',
                user_id=request.user.id,
                resource='Patient',
                resource_id=obj.patient.id,
                action=request.method,
                status='failure'
            )
            
            logger.warning(
                'Permission denied',
                user_id=request.user.id,
                resource='Patient',
                resource_id=obj.patient.id
            )
        
        return is_allowed


# ============================================================================
# 7. FILTERS & QUERYSETS - Query Logging
# ============================================================================

from django_filters import rest_framework as filters


class PatientFilter(filters.FilterSet):
    """
    Example: Filter with logging
    """
    class Meta:
        model = Patient
        fields = ['name', 'email']
    
    def filter_queryset(self, queryset):
        """Log filter operations"""
        filter_params = dict(self.data)
        
        logger.debug(
            'Applied patient filters',
            filters=filter_params,
            result_count=queryset.count()
        )
        
        return super().filter_queryset(queryset)


# ============================================================================
# 8. MANAGEMENT COMMANDS - Admin Task Logging
# ============================================================================

from django.core.management.base import BaseCommand
from smartcare_hms.logging_utils import LogExecutionTime


class Command(BaseCommand):
    """
    Example: Management command with performance logging
    
    Usage: python manage.py example_command
    """
    help = 'Example management command with logging'
    
    def add_arguments(self, parser):
        parser.add_argument('--tenant-id', type=int)
    
    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        
        with LogExecutionTime('example_command'):
            logger.info('Starting example command', tenant_id=tenant_id)
            
            try:
                # Your command logic here
                patients = Patient.objects.all()
                
                for patient in patients:
                    logger.debug(f'Processing patient {patient.id}')
                
                logger.info(
                    'Command completed successfully',
                    processed=patients.count(),
                    tenant_id=tenant_id
                )
                
            except Exception as e:
                logger.error(
                    'Command failed',
                    exception=e,
                    tenant_id=tenant_id
                )
                raise


# ============================================================================
# 9. CONTEXT MANAGERS - Structured Operation Logging
# ============================================================================

from contextlib import contextmanager


@contextmanager
def log_operation(operation_name, **context):
    """
    Example: Context manager for logging operations
    
    Usage:
        with log_operation('process_payment', patient_id=123, amount=5000):
            # payment logic
    """
    logger.info(f'{operation_name} started', **context)
    start_time = time.time()
    
    try:
        yield
        
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f'{operation_name} completed',
            duration_ms=round(duration_ms, 2),
            **context
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            f'{operation_name} failed',
            exception=e,
            duration_ms=round(duration_ms, 2),
            **context
        )
        raise


# Usage example
def process_payment(patient_id, amount):
    with log_operation('process_payment', patient_id=patient_id, amount=amount):
        # Payment processing logic
        pass


# ============================================================================
# 10. MIDDLEWARE - Custom Request Logging
# ============================================================================

from django.utils.deprecation import MiddlewareMixin
import json


class CustomAuditMiddleware(MiddlewareMixin):
    """
    Example: Custom middleware for audit logging
    """
    
    def process_request(self, request):
        """Log incoming request details"""
        if self._should_audit(request):
            audit_data = {
                'method': request.method,
                'path': request.path,
                'user': request.user.username if request.user.is_authenticated else 'Anonymous',
                'ip': self._get_client_ip(request),
            }
            logger.debug('Request received', **audit_data)
        return None
    
    def _should_audit(self, request):
        """Determine if request should be audited"""
        excluded_paths = ['/health/', '/metrics/', '/static/']
        return not any(request.path.startswith(path) for path in excluded_paths)
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


# ============================================================================
# INTEGRATION CHECKLIST
# ============================================================================
"""
To integrate logging into your Django apps:

1. VIEWS:
   ✓ Import logger and audit functions at the top
   ✓ Wrap try/except blocks with logging
   ✓ Log user actions (CREATE, UPDATE, DELETE)
   ✓ Include correlation IDs from request.correlation_id

2. MODELS:
   ✓ Override save() and delete() to log changes
   ✓ Use log_audit_event() for compliance
   ✓ Track field changes in UPDATE events

3. SIGNALS:
   ✓ Add signal handlers for model changes
   ✓ Log important events (post_save, post_delete)

4. CELERY TASKS:
   ✓ Log task start and completion
   ✓ Include duration and result
   ✓ Catch and log exceptions

5. PERMISSIONS:
   ✓ Log permission denials
   ✓ Use log_security_event() for security events

6. MANAGEMENT COMMANDS:
   ✓ Use LogExecutionTime context manager
   ✓ Log progress and completion

7. TESTING:
   ✓ Test that logs are created correctly
   ✓ Verify sensitive data is not logged
   ✓ Check log format and structure
"""
