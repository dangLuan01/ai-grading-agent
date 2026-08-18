from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db


async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_check(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_ready_check_returns_structured_error_when_database_unavailable(
    app: FastAPI,
) -> None:
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("database down")

    async def override_get_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


async def test_login_and_me(client: AsyncClient, user_factory) -> None:
    user_factory(email="teacher@example.com", password="secret-pass")

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "teacher@example.com", "password": "secret-pass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "teacher@example.com"
    assert me_response.json()["role"] == "TEACHER"


async def test_login_rejects_invalid_password(client: AsyncClient, user_factory) -> None:
    user_factory(email="teacher@example.com", password="secret-pass")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "teacher@example.com", "password": "wrong-pass"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
