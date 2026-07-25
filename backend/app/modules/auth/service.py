from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import SecurityManager
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse, LoginUser


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
        user.last_login_at = datetime.now(UTC)
        await self.session.commit()
        return LoginResponse(
            access_token=token,
            expires_in=expires_in,
            user=LoginUser(
                id=user.public_id,
                tenant_id=tenant.public_id,
                display_name=user.display_name,
                email=user.email,
                permissions=sorted(permissions),
            ),
        )
