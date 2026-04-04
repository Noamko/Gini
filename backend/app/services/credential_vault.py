"""Credential vault — Fernet encryption for sensitive values."""
import base64
import hashlib

import structlog
from cryptography.fernet import Fernet

from app.config import settings

logger = structlog.get_logger("credential_vault")


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the encryption_key setting."""
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not set — cannot encrypt/decrypt credentials")
    # Ensure we have a valid 32-byte base64-encoded key for Fernet
    # If the user provides a passphrase, derive a proper key
    raw = hashlib.sha256(key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(raw)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext value and return base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext and return plaintext."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
