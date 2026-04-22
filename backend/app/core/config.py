import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")


def _require_env(name: str, value: str | None) -> str:
    if value:
        return value
    raise RuntimeError(f"{name} must be configured")


def _normalize_app_env(value: str | None) -> str:
    normalized = (value or "production").strip().lower()
    if normalized in {"dev", "development", "local"}:
        return "development"
    if normalized in {"prod"}:
        return "production"
    return normalized or "production"


class Settings(BaseSettings):
    app_name: str = "Chit Fund Platform"
    app_env: str = "production"
    database_url: str = Field(default_factory=lambda: _require_env("DATABASE_URL", DATABASE_URL))
    jwt_secret: str = Field(default_factory=lambda: _require_env("JWT_SECRET", JWT_SECRET))
    database_pool_size: int | None = None
    database_max_overflow: int | None = None
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800
    structured_logging: bool | None = None
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int | None = None
    redis_socket_connect_timeout_seconds: float = 5.0
    redis_socket_timeout_seconds: float = 5.0
    redis_health_check_interval_seconds: int = 30
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_broker_pool_limit: int = 10
    celery_task_ignore_result: bool | None = None
    celery_task_always_eager: bool | None = None
    celery_task_store_errors_even_if_ignored: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED",
            "CELERY_STORE_ERRORS_EVEN_IF_IGNORED",
        ),
    )
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_worker_state_db: str | None = None
    celery_auto_close_interval_seconds: int = 60
    celery_pending_notification_interval_seconds: int = 60
    payment_reminder_hour_ist: int = 9
    notification_cleanup_hour_ist: int = 2
    job_run_cleanup_hour_ist: int = 3
    job_run_retention_days: int = 14
    read_notification_retention_days: int = 30
    default_page_size: int | None = None
    max_page_size: int | None = None
    smtp_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_HOST", "EMAIL_SMTP_HOST"),
    )
    smtp_port: int = Field(
        default=587,
        validation_alias=AliasChoices("SMTP_PORT", "EMAIL_SMTP_PORT"),
    )
    smtp_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_USERNAME", "EMAIL_SMTP_USERNAME"),
    )
    smtp_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_PASSWORD", "EMAIL_SMTP_PASSWORD"),
    )
    smtp_from_address: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_FROM_ADDRESS", "EMAIL_SMTP_FROM_ADDRESS"),
    )
    smtp_use_tls: bool = Field(
        default=True,
        validation_alias=AliasChoices("SMTP_USE_TLS", "EMAIL_SMTP_USE_TLS"),
    )
    smtp_use_ssl: bool = Field(
        default=False,
        validation_alias=AliasChoices("SMTP_USE_SSL", "EMAIL_SMTP_USE_SSL"),
    )
    smtp_timeout_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices("SMTP_TIMEOUT_SECONDS", "EMAIL_SMTP_TIMEOUT_SECONDS"),
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]
    )
    log_level: str = "info"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    auth_login_max_attempts: int = 5
    auth_login_attempt_window_seconds: int = 900
    auth_login_cooldown_seconds: int = 300
    sms_enabled: bool = False
    sms_provider: str | None = None

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _apply_celery_defaults(self):
        self.app_env = _normalize_app_env(self.app_env)

        if self.structured_logging is None:
            self.structured_logging = self.app_env == "production"
        if self.redis_max_connections is None:
            self.redis_max_connections = 20 if self.app_env == "production" else 5
        if self.celery_task_ignore_result is None:
            self.celery_task_ignore_result = self.app_env == "development"
        if self.celery_task_always_eager is None:
            self.celery_task_always_eager = self.app_env == "development"
        if self.database_pool_size is None:
            self.database_pool_size = 8 if self.app_env == "production" else 1
        if self.database_max_overflow is None:
            self.database_max_overflow = 16 if self.app_env == "production" else 0
        if self.default_page_size is None:
            self.default_page_size = 50 if self.app_env == "production" else 20
        if self.max_page_size is None:
            self.max_page_size = 200 if self.app_env == "production" else 50
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url
        return self

    @property
    def is_dev_profile(self) -> bool:
        return _normalize_app_env(self.app_env) == "development"

    @property
    def is_production_profile(self) -> bool:
        return _normalize_app_env(self.app_env) == "production"

    @property
    def celery_store_errors_even_if_ignored(self) -> bool:
        return self.celery_task_store_errors_even_if_ignored

    @property
    def email_delivery_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_address)


settings = Settings()
