from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import SecurityManager
from app.db.session import get_db
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse
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
