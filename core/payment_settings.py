from .models import SystemSetting


PAYMENT_SETTING_KEYS = {
    'subscription_payment_method',
    'paystack_secret_key',
    'paystack_public_key',
    'paypal_client_id',
    'paypal_client_secret',
    'paypal_webhook_id',
    'paypal_base_url',
}


def get_payment_setting(key, default=''):
    if key not in PAYMENT_SETTING_KEYS:
        raise ValueError(f'Unsupported payment setting: {key}')
    setting = SystemSetting.objects.filter(key=key).first()
    if not setting:
        return default
    return setting.secret_value if setting.is_secret else setting.value


def payment_setting_configured(key):
    return bool(get_payment_setting(key, '').strip())


def set_payment_setting(key, value):
    if key not in PAYMENT_SETTING_KEYS:
        raise ValueError(f'Unsupported payment setting: {key}')
    secret_keys = {
        'paystack_secret_key', 'paypal_client_secret', 'paypal_webhook_id'
    }
    is_secret = key in secret_keys
    setting, _ = SystemSetting.objects.get_or_create(
        key=key,
        defaults={
            'value': '' if is_secret else str(value),
            'secret_value': str(value) if is_secret else '',
            'is_secret': is_secret,
            'category': 'payment',
            'description': 'Payment gateway configuration',
        },
    )
    setting.is_secret = is_secret
    if is_secret:
        if value:
            setting.secret_value = str(value)
    else:
        setting.value = str(value)
    setting.save(update_fields=['value', 'secret_value', 'is_secret'])