from typing import Annotated

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
DbSession = Annotated[Session, Depends(get_db)]


async def get_current_user(
    credentials: BearerCredentials,
    db: DbSession,
) -> User:
    if credentials is None:
        raise DomainError(
            ErrorCode.UNAUTHORIZED,
            "Authentication credentials were not provided.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        user_id = int(subject)
    except (PyJWTError, TypeError, ValueError):
        raise DomainError(
            ErrorCode.UNAUTHORIZED,
            "Authentication token is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from None

    user = db.get(User, user_id)
    if user is None:
        raise DomainError(
            ErrorCode.UNAUTHORIZED,
            "Authentication token is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        raise DomainError(
            ErrorCode.INACTIVE_USER,
            "User account is inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user
