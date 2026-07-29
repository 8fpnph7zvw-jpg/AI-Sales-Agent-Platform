from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import SecurityManager
from app.db.base import new_ulid
from app.models.auth.auth_session import AuthSession
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse, LoginUser, RefreshTokenRequest


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        repository: AuthRepository,
        security: SecurityManager,
    ) -> None:
        self.session = session
        self.repository = repository
        self.security = security

    async def login(self, payload: LoginRequest) -> LoginResponse:
        identity = await self.repository.get_login_identity(
            payload.tenant_slug,
            payload.email,
        )
        if identity is None:
            self.security.verify_password(payload.password, None)
            raise AuthenticationError("Tenant, email, or password is incorrect.")

        user, tenant = identity
        password_valid = self.security.verify_password(payload.password, user.password_hash)
        if not password_valid or user.status != "active" or tenant.status != "active":
            raise AuthenticationError("Tenant, email, or password is incorrect.")

        permissions = await self.repository.get_permission_codes(user.id)
        token, expires_in = self.security.create_access_token(
            user.public_id,
            tenant.public_id,
        )
        refresh_token, refresh_hash, refresh_expires_at, refresh_expires_in = (
            self.security.create_refresh_token()
        )
        self.repository.add_auth_session(
            AuthSession(
                tenant_id=tenant.id,
                user_id=user.id,
                refresh_token_hash=refresh_hash,
                token_family_id=new_ulid(),
                expires_at=refresh_expires_at,
            )
        )
        user.last_login_at = datetime.now(UTC)
        await self.session.commit()
        return LoginResponse(
            access_token=token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            user=LoginUser(
                id=user.public_id,
                tenant_id=tenant.public_id,
                display_name=user.display_name,
                email=user.email,
                permissions=sorted(permissions),
            ),
        )

    async def refresh(self, payload: RefreshTokenRequest) -> LoginResponse:
        now = datetime.now(UTC)
        context = await self.repository.get_refresh_session(
            self.security.hash_refresh_token(payload.refresh_token)
        )
        if context is None:
            raise AuthenticationError("Refresh token is invalid or revoked.")

        auth_session, user, tenant = context
        if (
            auth_session.expires_at <= now
            or user.status != "active"
            or tenant.status != "active"
        ):
            auth_session.revoked_at = now
            auth_session.revoke_reason = "expired_or_inactive"
            await self.session.commit()
            raise AuthenticationError("Refresh token is expired or inactive.")

        refresh_token, refresh_hash, refresh_expires_at, refresh_expires_in = (
            self.security.create_refresh_token()
        )
        auth_session.refresh_token_hash = refresh_hash
        auth_session.expires_at = refresh_expires_at
        auth_session.last_used_at = now
        token, expires_in = self.security.create_access_token(
            user.public_id,
            tenant.public_id,
        )
        permissions = await self.repository.get_permission_codes(user.id)
        await self.session.commit()
        return LoginResponse(
            access_token=token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            user=LoginUser(
                id=user.public_id,
                tenant_id=tenant.public_id,
                display_name=user.display_name,
                email=user.email,
                permissions=sorted(permissions),
            ),
        )

    async def logout(self, payload: RefreshTokenRequest) -> None:
        context = await self.repository.get_refresh_session(
            self.security.hash_refresh_token(payload.refresh_token)
        )
        if context is None:
            return
        auth_session, _, _ = context
        auth_session.revoked_at = datetime.now(UTC)
        auth_session.revoke_reason = "user_logout"
        await self.session.commit()
