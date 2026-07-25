from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ServiceConfigurationError

password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-user-password-sentinel")


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_public_id: str
    tenant_public_id: str


class SecurityManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify_password(self, password: str, password_hash: str | None) -> bool:
        candidate_hash = password_hash or DUMMY_PASSWORD_HASH
        try:
            password_hasher.verify(candidate_hash, password)
            return password_hash is not None
        except (VerifyMismatchError, VerificationError):
            return False

    def hash_password(self, password: str) -> str:
        return password_hasher.hash(password)

    def create_access_token(self, user_public_id: str, tenant_public_id: str) -> tuple[str, int]:
        secret = self._jwt_secret()
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.settings.access_token_expire_minutes)
        payload = {
            "sub": user_public_id,
            "tid": tenant_public_id,
            "type": "access",
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
        }
        token = jwt.encode(payload, secret, algorithm=self.settings.jwt_algorithm)
        return token, int((expires_at - now).total_seconds())

    def decode_access_token(self, token: str) -> TokenClaims:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._jwt_secret(),
                algorithms=[self.settings.jwt_algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "tid", "type"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Access token is invalid or expired.") from exc

        if payload.get("type") != "access":
            raise AuthenticationError("Access token type is invalid.")
        return TokenClaims(
            user_public_id=str(payload["sub"]),
            tenant_public_id=str(payload["tid"]),
        )

    def _jwt_secret(self) -> str:
        if len(self.settings.jwt_secret) < 32:
            raise ServiceConfigurationError("JWT_SECRET must contain at least 32 characters.")
        return self.settings.jwt_secret
