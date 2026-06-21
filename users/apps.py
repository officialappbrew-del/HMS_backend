# from django.db.models.signals import post_save, pre_delete, pre_save
# from django.dispatch import receiver
# from django.utils import timezone

# from .models import GlobalUser, User2FA, RSAKey, SecurityEvent


# @receiver(post_save, sender=GlobalUser)
# def create_user_2fa_settings(sender, instance, created, **kwargs):
#     """Create 2FA settings when a new user is created."""
#     if created and not hasattr(instance, 'two_fa_settings'):
#         User2FA.objects.create(user=instance)


# @receiver(post_save, sender=GlobalUser)
# def log_user_changes(sender, instance, created, **kwargs):
#     """Log user creation and updates."""
#     from apps.core.models import AuditLog
    
#     action = 'create_user' if created else 'update_user'
    
#     # Don't log password changes (they're handled separately)
#     if 'password' in instance._state.fields_to_save:
#         return
    
#     AuditLog.objects.create(
#         user=instance,
#         action=action,
#         resource_type='user',
#         resource_id=str(instance.id),
#         new_values={
#             'username': instance.username,
#             'email': instance.email,
#             'role': instance.role,
#             'is_active': instance.is_active
#         }
#     )


# @receiver(pre_save, sender=GlobalUser)
# def check_account_lock(sender, instance, **kwargs):
#     """Check if account should be locked due to too many failed attempts."""
#     if instance.login_attempts >= 5 and not instance.account_locked_until:
#         instance.lock_account()


# @receiver(post_save, sender=RSAKey)
# def set_primary_key(sender, instance, created, **kwargs):
#     """Ensure only one primary RSA key per user."""
#     if instance.is_primary:
#         RSAKey.objects.filter(
#             user=instance.user,
#             is_primary=True
#         ).exclude(id=instance.id).update(is_primary=False)


# @receiver(pre_delete, sender=RSAKey)
# def log_key_deletion(sender, instance, **kwargs):
#     """Log RSA key deletion."""
#     from apps.core.models import AuditLog
    
#     AuditLog.objects.create(
#         user=instance.user,
#         action='delete_rsa_key',
#         resource_type='rsa_key',
#         resource_id=str(instance.id),
#         old_values={
#             'key_name': instance.key_name,
#             'key_fingerprint': instance.key_fingerprint
#         }
#     )

from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
