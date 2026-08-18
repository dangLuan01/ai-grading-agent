from app.core.config import Settings


def test_default_database_url_targets_mysql_with_utf8mb4() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("mysql+pymysql://")
    assert "charset=utf8mb4" in settings.database_url


def test_size_limits_expose_byte_values() -> None:
    settings = Settings(max_repository_size_mb=50, max_file_size_mb=10, _env_file=None)

    assert settings.max_repository_size_bytes == 50 * 1024 * 1024
    assert settings.max_file_size_bytes == 10 * 1024 * 1024
