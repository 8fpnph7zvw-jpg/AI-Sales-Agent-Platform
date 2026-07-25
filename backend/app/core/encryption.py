from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError


class ConfigCipher:
    """AES-256-GCM envelope for connector and system configuration values."""

    def __init__(self, settings: Settings) -> None:
        self.key_version = settings.config_encryption_key_version
        self._encoded_key = settings.config_encryption_key

    def encrypt(self, value: Any, *, associated_data: str) -> bytes:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        ciphertext = AESGCM(self._key()).encrypt(
            nonce,
            plaintext,
            associated_data.encode(),
        )
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes, *, associated_data: str) -> Any:
        nonce, ciphertext = encrypted[:12], encrypted[12:]
        plaintext = AESGCM(self._key()).decrypt(
            nonce,
            ciphertext,
            associated_data.encode(),
        )
        return json.loads(plaintext)

    def _key(self) -> bytes:
        return self._decode_key(self._encoded_key)

    @staticmethod
    def _decode_key(value: str) -> bytes:
        try:
            padded = value + "=" * (-len(value) % 4)
            key = base64.urlsafe_b64decode(padded)
        except (ValueError, TypeError) as exc:
            raise ServiceConfigurationError(
                "CONFIG_ENCRYPTION_KEY must be URL-safe base64."
            ) from exc
        if len(key) != 32:
            raise ServiceConfigurationError(
                "CONFIG_ENCRYPTION_KEY must decode to exactly 32 bytes."
            )
        return key
