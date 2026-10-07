from functools import lru_cache
from typing import List, Literal, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "NexusCRM"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_URL: str = "http://localhost:3000"
    API_V1_PREFIX: str = "/api/v1"

    # Security & Tokens
    SECRET_KEY: str = "nexuscrm_super_secret_development_key_change_in_production_1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    # Primary default is PostgreSQL; SQLite async supported for local lightweight testing
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nexuscrm"
    SYNC_DATABASE_URL: Optional[str] = "postgresql://postgres:postgres@localhost:5432/nexuscrm"

    # Redis & Workers
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # AI Intelligence Layer
    AI_PROVIDER: Literal["mock", "openai", "gemini", "anthropic"] = "mock"
    AI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gpt-4o-mini"
    AI_TEMPERATURE: float = 0.7

    # Storage Provider Abstraction
    STORAGE_PROVIDER: Literal["local", "minio", "s3"] = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"
    S3_ENDPOINT: Optional[str] = "http://localhost:9000"
    S3_BUCKET: str = "nexuscrm-uploads"
    S3_ACCESS_KEY: Optional[str] = "minioadmin"
    S3_SECRET_KEY: Optional[str] = "minioadmin"
    S3_REGION: str = "us-east-1"

    # Email Provider Abstraction
    EMAIL_PROVIDER: Literal["mock", "smtp", "sendgrid", "resend"] = "mock"
    EMAIL_FROM: str = "no-reply@nexuscrm.local"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Calendar Integration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/calendar/oauth2callback"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000"]


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()
