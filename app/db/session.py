from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session

from app.db.database import SessionLocal


async def get_db() -> AsyncGenerator[Session, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
