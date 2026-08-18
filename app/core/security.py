from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings, get_settings

MAX_BCRYPT_PASSWORD_BYTES = 72


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or fewer for bcrypt.")
    return encoded


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    active_settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + (
        expires_delta or timedelta(minutes=active_settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(
        payload,
        active_settings.jwt_secret,
        algorithm=active_settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    return jwt.decode(
        token,
        active_settings.jwt_secret,
        algorithms=[active_settings.jwt_algorithm],
    )
