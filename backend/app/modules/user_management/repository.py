from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.permission import Permission
from app.models.auth.role import Role
from app.models.auth.role_permission import RolePermission
from app.models.auth.sales_profile import SalesProfile
from app.models.auth.user import User
from app.models.auth.user_role import UserRole

SALES_PERMISSIONS = {
    "dashboard.read",
    "customer.read_own",
    "customer.create",
    "customer.update_own",
    "conversation.read_own",
    "message.send",
    "product.read",
    "quotation.read_own",
    "quotation.create",
    "quotation.update_own",
    "customer.score_read",
}


class UserManagementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, tenant_id: int) -> list[tuple[User, SalesProfile | None, str | None]]:
        return list(
            (
                await self.session.execute(
                    select(User, SalesProfile, Role.code)
                    .outerjoin(SalesProfile, SalesProfile.user_id == User.id)
                    .outerjoin(UserRole, UserRole.user_id == User.id)
                    .outerjoin(Role, Role.id == UserRole.role_id)
                    .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
                    .order_by(User.created_at.desc())
                )
            ).tuples()
        )

    async def get(self, tenant_id: int, public_id: str, *, for_update: bool = False) -> User | None:
        statement = select(User).where(
            User.tenant_id == tenant_id,
            User.public_id == public_id,
            User.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_by_email(self, tenant_id: int, email: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == email)
        )

    async def profile(self, user_id: int) -> SalesProfile | None:
        return await self.session.scalar(
            select(SalesProfile).where(SalesProfile.user_id == user_id)
        )

    async def ensure_sales_role(self, tenant_id: int) -> Role:
        role = await self.session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.code == "sales")
        )
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                code="sales",
                name="Sales",
                description="Sales users restricted to their own business data.",
                is_system=True,
            )
            self.session.add(role)
            await self.session.flush()
        permission_ids = set(
            (
                await self.session.scalars(
                    select(Permission.id).where(Permission.code.in_(SALES_PERMISSIONS))
                )
            ).all()
        )
        assigned = set(
            (
                await self.session.scalars(
                    select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                )
            ).all()
        )
        self.session.add_all(
            RolePermission(role_id=role.id, permission_id=permission_id)
            for permission_id in permission_ids - assigned
        )
        return role

    async def role_code(self, user_id: int) -> str | None:
        return await self.session.scalar(
            select(Role.code).join(UserRole).where(UserRole.user_id == user_id).limit(1)
        )

    async def clear_roles(self, user_id: int) -> None:
        await self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))

    async def total(self, tenant_id: int) -> int:
        return int(
            (
                await self.session.scalar(
                    select(func.count(User.id)).where(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None),
                    )
                )
            )
            or 0
        )
