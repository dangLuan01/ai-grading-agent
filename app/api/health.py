from fastapi import APIRouter, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.core.exceptions import DomainError, ErrorCode

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise DomainError(
            ErrorCode.DATABASE_UNAVAILABLE,
            "Database is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    return {"status": "ready", "database": "ok"}
