from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HarnessQuest"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://harnessquest:harnessquest@app-postgres:5432/harnessquest"
    redis_url: str = "redis://redis:***@harnessquest.local"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    upload_dir: str = "uploads/images"

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

    oauth_enabled: bool = False
    oauth_provider: str = "oidc"
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_redirect_uri: str | None = None
    oauth_authorization_url: str | None = None
    oauth_token_url: str | None = None
    oauth_userinfo_url: str | None = None
    oauth_email_url: str | None = None
    oauth_scope: str = "openid email profile"

    # OAuth -> User field mapping.
    # Dot-path with | fallback chain, e.g. OAUTH_MAP_EMAIL=mail|userPrincipalName
    # When None, uses the current hardcoded fallback logic.
    oauth_map_email: str | None = None
    oauth_map_display_name: str | None = None


    bootstrap_admin_email: str = "admin@harnessquest.local"
    bootstrap_admin_password: str = "admin123456"
    bootstrap_admin_name: str = "Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
