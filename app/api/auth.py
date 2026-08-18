from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import DomainError, ErrorCode
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = auth_service.authenticate_user(db, str(payload.email), payload.password)
    if user is None:
        raise DomainError(
            ErrorCode.INVALID_CREDENTIALS,
            "Email or password is incorrect.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        raise DomainError(
            ErrorCode.INACTIVE_USER,
            "User account is inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    settings = get_settings()
    token = create_access_token(str(user.id), settings=settings)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: CurrentUser) -> User:
    return current_user
