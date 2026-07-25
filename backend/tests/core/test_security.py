from __future__ import annotations

import base64
import os

import pytest

from app.core.config import Settings
from app.core.encryption import ConfigCipher
from app.core.exceptions import ServiceConfigurationError
from app.core.security import SecurityManager


def _settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "a-secure-test-secret-with-more-than-32-characters",
        "config_encryption_key": base64.urlsafe_b64encode(os.urandom(32)).decode(),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_password_hash_and_jwt_round_trip() -> None:
    security = SecurityManager(_settings())
    password_hash = security.hash_password("correct horse battery staple")

    assert security.verify_password("correct horse battery staple", password_hash)
    assert not security.verify_password("wrong password", password_hash)

    token, expires_in = security.create_access_token("01USER", "01TENANT")
    claims = security.decode_access_token(token)
    assert claims.user_public_id == "01USER"
    assert claims.tenant_public_id == "01TENANT"
    assert expires_in == 15 * 60


def test_connector_config_cipher_uses_authenticated_encryption() -> None:
    cipher = ConfigCipher(_settings())
    encrypted = cipher.encrypt(
        {"token": "secret"},
        associated_data="1:2:access_token",
    )

    assert b"secret" not in encrypted
    assert cipher.decrypt(
        encrypted,
        associated_data="1:2:access_token",
    ) == {"token": "secret"}


def test_connector_cipher_rejects_missing_key_when_used() -> None:
    cipher = ConfigCipher(_settings(config_encryption_key=""))

    with pytest.raises(ServiceConfigurationError):
        cipher.encrypt("secret", associated_data="1:2:key")
