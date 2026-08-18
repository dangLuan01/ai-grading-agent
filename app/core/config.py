from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me"
MIN_PRODUCTION_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Assignment Grading Agent"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = (
        "mysql+pymysql://ai_grading:change_me@mysql-host:3306/ai_grading?charset=utf8mb4"
    )

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    github_token: str | None = None

    llm_primary_provider: str = "gemini"
    llm_fallback_provider: str = "qwen"

    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: str | None = None
    gemini_model: str | None = None

    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_api_key: str | None = None
    qwen_model: str | None = None

    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str | None = None
    deepseek_model: str | None = None

    llm_timeout_seconds: int = 60

    max_repository_size_mb: int = Field(default=50, ge=1)
    max_file_size_mb: int = Field(default=10, ge=1)
    max_parsed_files: int = Field(default=200, ge=1)

    max_regrade_attempts: int = Field(default=1, ge=0)

    grading_temp_dir: str = "/tmp/grading"

    @property
    def max_repository_size_bytes(self) -> int:
        return self.max_repository_size_mb * 1024 * 1024

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.lower() != "production":
            return self

        jwt_secret = self.jwt_secret.strip()
        if not jwt_secret:
            raise ValueError("JWT_SECRET is required when APP_ENV=production.")
        if jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be changed when APP_ENV=production.")
        if len(jwt_secret.encode("utf-8")) < MIN_PRODUCTION_JWT_SECRET_BYTES:
            raise ValueError(
                "JWT_SECRET must be at least 32 bytes when APP_ENV=production."
            )
        if len(set(jwt_secret)) < 8:
            raise ValueError("JWT_SECRET is too weak when APP_ENV=production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
