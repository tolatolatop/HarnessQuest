from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HarnessQuest"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://harnessquest:harnessquest@app-postgres:5432/harnessquest"
    redis_url: str = "redis://redis:6379/1"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    minio_endpoint_url: str = "http://minio:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "miniosecret"
    minio_bucket: str = "harnessquest"
    minio_region: str = "us-east-1"

    langfuse_base_url: str = "http://langfuse-web:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    analyzer_base_url: str | None = None
    analyzer_api_key: str | None = None
    analyzer_model: str = "deepseek-chat"
    analyzer_timeout_seconds: int = 60

    oidc_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None

    bootstrap_admin_email: str = "admin@harnessquest.local"
    bootstrap_admin_password: str = "admin123456"
    bootstrap_admin_name: str = "Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
