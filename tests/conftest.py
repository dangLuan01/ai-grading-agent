import os
from collections.abc import AsyncGenerator, Generator

os.environ["JWT_SECRET"] = "unit-test-secret-with-at-least-32-bytes"

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def app(db_session: Session) -> FastAPI:
    application = create_app()

    async def override_get_db() -> AsyncGenerator[Session, None]:
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture()
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


def create_user(
    db_session: Session,
    *,
    email: str = "teacher@example.com",
    password: str = "correct horse battery staple",
    role: UserRole = UserRole.TEACHER,
    is_active: bool = True,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role.value,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def user_factory(db_session: Session):
    def factory(**kwargs) -> User:
        return create_user(db_session, **kwargs)

    return factory


@pytest.fixture()
async def auth_headers(client: AsyncClient, user_factory) -> dict[str, str]:
    user_factory(email="teacher@example.com", password="secret-pass")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "teacher@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
