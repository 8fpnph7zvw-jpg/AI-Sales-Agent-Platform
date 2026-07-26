from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.security import password_hasher
from app.db.session import AsyncSessionLocal, dispose_engine
from app.models.auth.permission import Permission
from app.models.auth.role import Role
from app.models.auth.role_permission import RolePermission
from app.models.auth.tenant import Tenant
from app.models.auth.user import User
from app.models.auth.user_role import UserRole

TENANT_NAME = "AI Sales Agent Demo"
TENANT_SLUG = "demo"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "Admin@2026"
OWNER_ROLE_CODE = "owner"


async def initialize_admin() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(
                select(Tenant).where(Tenant.slug == TENANT_SLUG).with_for_update()
            )
            if tenant is None:
                tenant = Tenant(
                    name=TENANT_NAME,
                    slug=TENANT_SLUG,
                    status="active",
                )
                session.add(tenant)
                await session.flush()
            else:
                tenant.name = TENANT_NAME

            owner_role = await session.scalar(
                select(Role)
                .where(
                    Role.tenant_id == tenant.id,
                    Role.code == OWNER_ROLE_CODE,
                )
                .with_for_update()
            )
            if owner_role is None:
                owner_role = Role(
                    tenant_id=tenant.id,
                    code=OWNER_ROLE_CODE,
                    name="Owner",
                    description="Tenant owner with full access.",
                    is_system=True,
                )
                session.add(owner_role)
                await session.flush()

            permission_ids = set((await session.scalars(select(Permission.id))).all())
            if not permission_ids:
                raise RuntimeError("Permission catalog is empty; run database migrations first.")

            assigned_permission_ids = set(
                (
                    await session.scalars(
                        select(RolePermission.permission_id).where(
                            RolePermission.role_id == owner_role.id
                        )
                    )
                ).all()
            )
            session.add_all(
                RolePermission(role_id=owner_role.id, permission_id=permission_id)
                for permission_id in permission_ids - assigned_permission_ids
            )

            user = await session.scalar(
                select(User)
                .where(
                    User.tenant_id == tenant.id,
                    User.email == ADMIN_EMAIL,
                )
                .with_for_update()
            )
            if user is None:
                user = User(
                    tenant_id=tenant.id,
                    email=ADMIN_EMAIL,
                    password_hash=password_hasher.hash(ADMIN_PASSWORD),
                    display_name="Administrator",
                    status="active",
                )
                session.add(user)
                await session.flush()

            user_role = await session.scalar(
                select(UserRole).where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == owner_role.id,
                )
            )
            if user_role is None:
                session.add(
                    UserRole(
                        user_id=user.id,
                        role_id=owner_role.id,
                        assigned_by=user.id,
                    )
                )

    print(
        f"Administrator initialized for tenant '{TENANT_SLUG}': {ADMIN_EMAIL}; "
        f"owner permissions: {len(permission_ids)}"
    )


async def main() -> None:
    try:
        await initialize_admin()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
