from datetime import timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_uses_bcrypt_and_verifies() -> None:
    password_hash = hash_password("s3cret-pass")

    assert password_hash.startswith("$2")
    assert verify_password("s3cret-pass", password_hash)
    assert not verify_password("wrong-pass", password_hash)


def test_create_and_decode_access_token() -> None:
    settings = Settings(jwt_secret="unit-test-secret-with-at-least-32-bytes", _env_file=None)

    token = create_access_token("123", settings=settings)
    payload = decode_access_token(token, settings=settings)

    assert payload["sub"] == "123"


def test_expired_access_token_is_rejected() -> None:
    settings = Settings(jwt_secret="unit-test-secret-with-at-least-32-bytes", _env_file=None)
    token = create_access_token("123", expires_delta=timedelta(seconds=-1), settings=settings)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, settings=settings)
