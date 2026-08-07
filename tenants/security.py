"""
Field-level encryption helpers for per-tenant communication credentials.

Uses Fernet (symmetric) with a key derived from ``settings.ENCRYPTION_KEY``.
If no usable key is available, encryption is disabled so the system still
works in development, but a warning is logged.
"""
import base64
import hashlib
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_prefix = "enc:"


def _load_fernet():
    from cryptography.fernet import Fernet, InvalidToken

    raw_key = str(getattr(settings, 'ENCRYPTION_KEY', '') or '').strip()
    if not raw_key or raw_key in {
        'your-32-char-key-for-encryption-change-this',
        'changeme',
    }:
        return None

    # Derive a stable 32-byte key from any provided passphrase so that a
    # normal salt/password can be used instead of a pre-generated base64 key.
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_value(value):
    """Encrypt a plaintext string, returning a prefixed ciphertext."""
    if not value:
        return value
    fernet = _load_fernet()
    if fernet is None:
        return value
    try:
        token = fernet.encrypt(str(value).encode('utf-8'))
        return _prefix + token.decode('utf-8')
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning('Encryption failed, storing plaintext: %s', exc)
        return value


def is_encrypted(value):
    """Return True if the value was produced by :func:`encrypt_value`."""
    return bool(value) and isinstance(value, str) and value.startswith(_prefix)


def decrypt_value(value):
    """Decrypt a value previously produced by :func:`encrypt_value`."""
    if not value:
        return value
    if not isinstance(value, str) or not value.startswith(_prefix):
        return value
    fernet = _load_fernet()
    if fernet is None:
        return value
    try:
        token = value[len(_prefix):]
        return fernet.decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception as exc:
        logger.warning('Decryption failed for stored value: %s', exc)
        return value

