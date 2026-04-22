import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings


def test_settings_expose_ergonomic_defaults(monkeypatch):
    for key in [
        "APP_ENV",
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS",
        "REDIS_SOCKET_TIMEOUT_SECONDS",
        "REDIS_HEALTH_CHECK_INTERVAL_SECONDS",
        "CELERY_BROKER_POOL_LIMIT",
        "DEFAULT_PAGE_SIZE",
        "MAX_PAGE_SIZE",
    ]:
        monkeypatch.delenv(key, raising=False)

    import app.core.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.app_env == "production"
    assert settings.is_production_profile is True
    assert settings.is_dev_profile is False
    assert settings.database_url == "sqlite:///./test-suite-bootstrap.db"
    assert settings.jwt_secret == "test-secret"
    assert settings.database_pool_size == 8
    assert settings.database_max_overflow == 16
    assert settings.database_pool_timeout_seconds == 30
    assert settings.database_pool_recycle_seconds == 1800
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.redis_max_connections == 20
    assert settings.redis_socket_connect_timeout_seconds == 5.0
    assert settings.redis_socket_timeout_seconds == 5.0
    assert settings.redis_health_check_interval_seconds == 30
    assert settings.celery_broker_url == "redis://localhost:6379/0"
    assert settings.celery_result_backend == "redis://localhost:6379/0"
    assert settings.celery_broker_pool_limit == 10
    assert settings.celery_task_ignore_result is False
    assert settings.celery_task_always_eager is False
    assert settings.celery_store_errors_even_if_ignored is True
    assert settings.celery_task_serializer == "json"
    assert settings.celery_result_serializer == "json"
    assert settings.default_page_size == 50
    assert settings.max_page_size == 200
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    assert settings.smtp_host is None
    assert settings.smtp_port == 587
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_from_address is None
    assert settings.smtp_use_tls is True
    assert settings.smtp_use_ssl is False
    assert settings.smtp_timeout_seconds == 10.0
    assert settings.email_delivery_enabled is False
    assert settings.log_level == "info"
    assert settings.rate_limit_requests == 60
    assert settings.rate_limit_window_seconds == 60
    assert settings.auth_login_max_attempts == 5
    assert settings.auth_login_attempt_window_seconds == 900
    assert settings.auth_login_cooldown_seconds == 300
    assert settings.sms_enabled is False
    assert settings.sms_provider is None


def test_settings_apply_dev_profile_defaults(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./tmp.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.delenv("STRUCTURED_LOGGING", raising=False)
    monkeypatch.delenv("REDIS_MAX_CONNECTIONS", raising=False)
    monkeypatch.delenv("CELERY_TASK_IGNORE_RESULT", raising=False)
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.delenv("DATABASE_POOL_SIZE", raising=False)
    monkeypatch.delenv("DATABASE_MAX_OVERFLOW", raising=False)
    monkeypatch.delenv("DEFAULT_PAGE_SIZE", raising=False)
    monkeypatch.delenv("MAX_PAGE_SIZE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://cache.internal:6379/2")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker.internal:6379/3")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://result.internal:6379/4")

    import app.core.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.app_env == "development"
    assert settings.is_dev_profile is True
    assert settings.structured_logging is False
    assert settings.database_pool_size == 1
    assert settings.database_max_overflow == 0
    assert settings.redis_url == "redis://cache.internal:6379/2"
    assert settings.redis_max_connections == 5
    assert settings.celery_broker_url == "redis://broker.internal:6379/3"
    assert settings.celery_result_backend == "redis://result.internal:6379/4"
    assert settings.celery_task_ignore_result is True
    assert settings.celery_task_always_eager is True
    assert settings.default_page_size == 20
    assert settings.max_page_size == 50


def test_settings_parse_env_overrides(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./tmp.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("REDIS_URL", "redis://cache.internal:6379/2")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "12")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "7")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("DATABASE_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "40")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL_SECONDS", "15")
    monkeypatch.setenv("STRUCTURED_LOGGING", "true")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker.internal:6379/3")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://result.internal:6379/4")
    monkeypatch.setenv("CELERY_BROKER_POOL_LIMIT", "18")
    monkeypatch.setenv("CELERY_TASK_IGNORE_RESULT", "true")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    monkeypatch.setenv("CELERY_STORE_ERRORS_EVEN_IF_IGNORED", "false")
    monkeypatch.setenv("CELERY_TASK_SERIALIZER", "pickle")
    monkeypatch.setenv("CELERY_RESULT_SERIALIZER", "pickle")
    monkeypatch.setenv("DEFAULT_PAGE_SIZE", "14")
    monkeypatch.setenv("MAX_PAGE_SIZE", "60")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com, https://admin.example.com")
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "465")
    monkeypatch.setenv("EMAIL_SMTP_USERNAME", "mailer@example.com")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("EMAIL_SMTP_FROM_ADDRESS", "notifications@example.com")
    monkeypatch.setenv("EMAIL_SMTP_USE_TLS", "false")
    monkeypatch.setenv("EMAIL_SMTP_USE_SSL", "true")
    monkeypatch.setenv("EMAIL_SMTP_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "120")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("AUTH_LOGIN_MAX_ATTEMPTS", "7")
    monkeypatch.setenv("AUTH_LOGIN_ATTEMPT_WINDOW_SECONDS", "600")
    monkeypatch.setenv("AUTH_LOGIN_COOLDOWN_SECONDS", "180")
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("SMS_PROVIDER", "twilio")

    import app.core.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.app_env == "development"
    assert settings.database_url == "sqlite:///./tmp.db"
    assert settings.jwt_secret == "super-secret"
    assert settings.database_pool_size == 12
    assert settings.database_max_overflow == 7
    assert settings.database_pool_timeout_seconds == 25
    assert settings.database_pool_recycle_seconds == 900
    assert settings.redis_url == "redis://cache.internal:6379/2"
    assert settings.redis_max_connections == 40
    assert settings.redis_socket_connect_timeout_seconds == 3.5
    assert settings.redis_socket_timeout_seconds == 4.5
    assert settings.redis_health_check_interval_seconds == 15
    assert settings.structured_logging is True
    assert settings.celery_broker_url == "redis://broker.internal:6379/3"
    assert settings.celery_result_backend == "redis://result.internal:6379/4"
    assert settings.celery_broker_pool_limit == 18
    assert settings.celery_task_ignore_result is True
    assert settings.celery_task_always_eager is False
    assert settings.celery_store_errors_even_if_ignored is False
    assert settings.celery_task_serializer == "pickle"
    assert settings.celery_result_serializer == "pickle"
    assert settings.default_page_size == 14
    assert settings.max_page_size == 60
    assert settings.cors_origins == [
        "https://example.com",
        "https://admin.example.com",
    ]
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 465
    assert settings.smtp_username == "mailer@example.com"
    assert settings.smtp_password == "smtp-secret"
    assert settings.smtp_from_address == "notifications@example.com"
    assert settings.smtp_use_tls is False
    assert settings.smtp_use_ssl is True
    assert settings.smtp_timeout_seconds == 3.5
    assert settings.email_delivery_enabled is True
    assert settings.log_level == "debug"
    assert settings.rate_limit_requests == 120
    assert settings.rate_limit_window_seconds == 30
    assert settings.auth_login_max_attempts == 7
    assert settings.auth_login_attempt_window_seconds == 600
    assert settings.auth_login_cooldown_seconds == 180
    assert settings.sms_enabled is True
    assert settings.sms_provider == "twilio"


def test_app_uses_configured_cors_origins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./cors-test.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    import app.core.config as config_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(main_module)

    client = TestClient(main_module.app)
    response = client.get("/api/health", headers={"Origin": "https://example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"


def test_app_handles_cors_preflight_for_configured_origins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./cors-test.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    import app.core.config as config_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(main_module)
    monkeypatch.setattr(main_module, "bootstrap_database", lambda: None)
    monkeypatch.setattr(main_module, "subscribe_to_all_auction_events", lambda: None)

    client = TestClient(main_module.app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_global_cors_wrap_preserves_headers_on_error_responses(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./cors-test.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    import app.core.config as config_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(main_module)

    failing_app = FastAPI()

    @failing_app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    client = TestClient(main_module.apply_global_cors(failing_app), raise_server_exceptions=False)
    response = client.get("/boom", headers={"Origin": "https://example.com"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_app_handles_browser_preflight_for_local_static_frontend(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./cors-test.db")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4173")

    import app.core.config as config_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(main_module)

    client = TestClient(main_module.app)
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
    assert response.headers["access-control-allow-credentials"] == "true"
