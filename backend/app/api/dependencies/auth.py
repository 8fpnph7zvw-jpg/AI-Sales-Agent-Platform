from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import SecurityManager
from app.db.session import get_db
from app.modules.auth.repository import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    user_public_id: str
    tenant_id: int
    tenant_public_id: str
    permissions: frozenset[str]


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Bearer access token is required.")

    claims = SecurityManager(get_settings()).decode_access_token(credentials.credentials)
    identity = await AuthRepository(session).get_principal(
        claims.user_public_id,
        claims.tenant_public_id,
    )
    if identity is None:
        raise AuthenticationError("User session is no longer active.")
    user, tenant, permissions = identity
    return Principal(
        user_id=user.id,
        user_public_id=user.public_id,
        tenant_id=tenant.id,
        tenant_public_id=tenant.public_id,
        permissions=frozenset(permissions),
    )


def require_any_permission(*permission_codes: str):
    async def permission_dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not principal.permissions.intersection(permission_codes):
            raise PermissionDeniedError()
        return principal

    return permission_dependency
