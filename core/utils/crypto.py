import base64
import hashlib
from typing import Optional

from django.conf import settings

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - cryptography should be installed via requirements
    Fernet = None  # type: ignore


def _derive_fernet_key_from_secret(secret: str) -> bytes:
    """Derive a 32-byte urlsafe base64 key for Fernet from Django SECRET_KEY."""
    # Stable derivation: SHA-256(secret) → 32 bytes → urlsafe_b64encode
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_text(plaintext: str) -> str:
    """Encrypt text using Fernet with a key derived from Django SECRET_KEY.

    Returns a urlsafe base64 token string. If cryptography is unavailable, returns plaintext.
    """
    if not plaintext:
        return ""
    if Fernet is None:
        # Fallback: return plaintext (should not happen in production)
        return plaintext
    key = _derive_fernet_key_from_secret(getattr(settings, "SECRET_KEY", "hotcalls-secret"))
    f = Fernet(key)
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(token: str) -> Optional[str]:
    """Decrypt a Fernet token back to text. Returns None if decryption fails.

    If cryptography is unavailable, returns the token as-is.
    """
    if not token:
        return ""
    if Fernet is None:
        return token
    try:
        key = _derive_fernet_key_from_secret(getattr(settings, "SECRET_KEY", "hotcalls-secret"))
        f = Fernet(key)
        data = f.decrypt(token.encode("utf-8"))
        return data.decode("utf-8")
    except Exception:
        return None


