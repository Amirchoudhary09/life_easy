"""Encryption at rest for OAuth tokens and other secrets stored in the database."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("cannot decrypt stored secret (key rotated?)") from exc


_box: SecretBox | None = None


def get_secret_box() -> SecretBox:
    """Fernet box from TOKEN_ENCRYPTION_KEY.

    Production refuses to start without a real key. Development derives a key
    from JWT_SECRET so OAuth flows can be tried locally.
    """
    global _box
    if _box is None:
        settings = get_settings()
        key = settings.token_encryption_key
        if not key:
            if settings.is_production:
                raise RuntimeError("TOKEN_ENCRYPTION_KEY is required in production")
            digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
            key = base64.urlsafe_b64encode(digest).decode("utf-8")
        _box = SecretBox(key)
    return _box


def reset_secret_box() -> None:
    global _box
    _box = None


def generate_key() -> str:
    """Helper for operators: `python -c "from app.security.crypto import generate_key; print(generate_key())"`."""
    return Fernet.generate_key().decode("utf-8")
