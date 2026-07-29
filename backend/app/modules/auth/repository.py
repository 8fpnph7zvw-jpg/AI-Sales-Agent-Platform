from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.auth_session import AuthSession
from app.models.auth.permission import Permission
from app.models.auth.role import Role
from app.models.auth.role_permission import RolePermission
from app.models.auth.tenant import Tenant
from app.models.auth.user import User
from app.models.auth.user_role import UserRole


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_login_identity(
        self,
        tenant_slug: str,
        email: str,
    ) -> tuple[User, Tenant] | None:
        statement = (
            select(User, Tenant)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                Tenant.slug == tenant_slug,
                Tenant.deleted_at.is_(None),
                User.email == email,
                User.deleted_at.is_(None),
            )
        )
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row else None

    async def get_principal(
        self,
        user_public_id: str,
        tenant_public_id: str,
    ) -> tuple[User, Tenant, set[str]] | None:
        statement = (
            select(User, Tenant)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                User.public_id == user_public_id,
                Tenant.public_id == tenant_public_id,
                User.status == "active",
                Tenant.status == "active",
                User.deleted_at.is_(None),
                Tenant.deleted_at.is_(None),
            )
        )
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        user, tenant = row
        permissions = await self.get_permission_codes(user.id)
        return user, tenant, permissions

    async def get_permission_codes(self, user_id: int) -> set[str]:
        statement = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        return set((await self.session.scalars(statement)).all())

    def add_auth_session(self, auth_session: AuthSession) -> None:
        self.session.add(auth_session)

    async def get_refresh_session(
        self,
        refresh_token_hash: str,
    ) -> tuple[AuthSession, User, Tenant] | None:
        statement = (
            select(AuthSession, User, Tenant)
            .join(
                User,
                (User.id == AuthSession.user_id)
                & (User.tenant_id == AuthSession.tenant_id),
            )
            .join(Tenant, Tenant.id == AuthSession.tenant_id)
            .where(
                AuthSession.refresh_token_hash == refresh_token_hash,
                AuthSession.revoked_at.is_(None),
                User.deleted_at.is_(None),
                Tenant.deleted_at.is_(None),
            )
            .with_for_update()
        )
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1], row[2]) if row else None
