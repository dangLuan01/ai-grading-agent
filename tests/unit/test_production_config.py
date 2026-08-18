import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET must be changed"):
        Settings(app_env="production", jwt_secret="change-me", _env_file=None)


def test_production_rejects_missing_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET is required"):
        Settings(app_env="production", jwt_secret="   ", _env_file=None)


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(app_env="production", jwt_secret="short-secret", _env_file=None)


def test_production_rejects_low_entropy_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="too weak"):
        Settings(app_env="production", jwt_secret="a" * 40, _env_file=None)


def test_production_accepts_strong_jwt_secret() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="strong-production-secret-1234567890",
        _env_file=None,
    )

    assert settings.jwt_secret == "strong-production-secret-1234567890"


def test_database_url_is_single_database_configuration_source() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("mysql+pymysql://")
    assert not hasattr(settings, "mysql_database")
    assert not hasattr(settings, "mysql_user")
    assert not hasattr(settings, "mysql_password")
    assert not hasattr(settings, "mysql_root_password")
