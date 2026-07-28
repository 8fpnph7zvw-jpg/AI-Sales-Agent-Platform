from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import Principal, get_current_principal
from app.core.config import get_settings
from app.core.security import SecurityManager
from app.db.session import get_db
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse, LoginUser
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthService:
    return AuthService(
        session=session,
        repository=AuthRepository(session),
        security=SecurityManager(get_settings()),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    return await service.login(payload)


@router.get("/me", response_model=LoginUser)
async def get_current_user(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> LoginUser:
    """Validate the access token and return the current server-side identity."""
    return LoginUser(
        id=principal.user_public_id,
        tenant_id=principal.tenant_public_id,
        display_name=principal.display_name,
        email=principal.email,
        permissions=sorted(principal.permissions),
    )
