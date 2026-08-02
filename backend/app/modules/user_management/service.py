from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.security import SecurityManager
from app.models.auth.sales_profile import SalesProfile
from app.models.auth.user import User
from app.models.auth.user_role import UserRole
from app.models.conversation.conversation import Conversation
from app.models.customer.customer import Customer
from app.modules.user_management.repository import UserManagementRepository
from app.modules.user_management.schemas import (
    SalesUserCreate,
    SalesUserListResponse,
    SalesUserRead,
    SalesUserUpdate,
)


class UserManagementService:
    def __init__(
        self,
        session: AsyncSession,
        repository: UserManagementRepository,
        security: SecurityManager,
    ) -> None:
        self.session = session
        self.repository = repository
        self.security = security

    async def list(self, principal: Principal) -> SalesUserListResponse:
        rows = await self.repository.list(principal.tenant_id)
        return SalesUserListResponse(
            data=[self._read(user, profile, role) for user, profile, role in rows],
            total=len(rows),
        )

    async def create(self, principal: Principal, payload: SalesUserCreate) -> SalesUserRead:
        existing = await self.repository.get_by_email(principal.tenant_id, payload.email)
        if existing and existing.deleted_at is None:
            raise ConflictError("USER_EMAIL_EXISTS", "A user with this email already exists.")
        role = await self.repository.ensure_sales_role(principal.tenant_id)
        user = User(
            tenant_id=principal.tenant_id,
            email=payload.email,
            password_hash=self.security.hash_password(payload.password),
            display_name=payload.display_name,
            status="active",
        )
        self.session.add(user)
        await self.session.flush()
        self.session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=principal.user_id))
        profile = SalesProfile(
            tenant_id=principal.tenant_id,
            user_id=user.id,
            sales_name=payload.sales_name,
            feishu_open_id=payload.feishu_open_id or None,
        )
        self.session.add(profile)
        await self._commit_conflicts()
        await self.session.refresh(user)
        return self._read(user, profile, "sales")

    async def update(
        self,
        principal: Principal,
        user_id: str,
        payload: SalesUserUpdate,
    ) -> SalesUserRead:
        user = await self.repository.get(principal.tenant_id, user_id, for_update=True)
        if user is None:
            raise ResourceNotFoundError("User")
        role = await self.repository.role_code(user.id)
        if role != "sales":
            raise ConflictError("ADMIN_USER_PROTECTED", "Only sales accounts can be changed here.")
        values = payload.model_dump(exclude_unset=True)
        if "display_name" in values:
            user.display_name = values["display_name"]
        if values.get("password"):
            user.password_hash = self.security.hash_password(values["password"])
        if "status" in values:
            user.status = values["status"]
        profile = await self.repository.profile(user.id)
        if profile is None:
            profile = SalesProfile(
                tenant_id=principal.tenant_id,
                user_id=user.id,
                sales_name=user.display_name,
            )
            self.session.add(profile)
        if "sales_name" in values:
            profile.sales_name = values["sales_name"]
        if "feishu_open_id" in values:
            profile.feishu_open_id = values["feishu_open_id"] or None
        await self._commit_conflicts()
        return self._read(user, profile, role)

    async def delete(self, principal: Principal, user_id: str) -> None:
        user = await self.repository.get(principal.tenant_id, user_id, for_update=True)
        if user is None:
            raise ResourceNotFoundError("User")
        if user.id == principal.user_id:
            raise ConflictError("SELF_DELETE_FORBIDDEN", "You cannot delete your own account.")
        if await self.repository.role_code(user.id) != "sales":
            raise ConflictError("ADMIN_USER_PROTECTED", "Only sales accounts can be deleted here.")
        await self.session.execute(
            update(Customer)
            .where(Customer.tenant_id == principal.tenant_id, Customer.owner_user_id == user.id)
            .values(owner_user_id=None)
        )
        await self.session.execute(
            update(Conversation)
            .where(
                Conversation.tenant_id == principal.tenant_id,
                Conversation.assigned_user_id == user.id,
            )
            .values(assigned_user_id=None)
        )
        user.status = "disabled"
        user.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def _commit_conflicts(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "SALES_PROFILE_CONFLICT", "Email or Feishu account is already bound."
            ) from exc

    @staticmethod
    def _read(user: User, profile: SalesProfile | None, role: str | None) -> SalesUserRead:
        return SalesUserRead(
            id=user.public_id,
            internal_id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            role="admin" if role == "owner" else (role or "sales"),
            sales_name=profile.sales_name if profile else None,
            feishu_open_id=profile.feishu_open_id if profile else None,
            created_at=user.created_at,
        )
