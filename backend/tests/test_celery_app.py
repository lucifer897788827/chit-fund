from types import SimpleNamespace

from app.core import config as config_module
from app.core.celery_app import build_celery_app, get_celery_config, worker_process_init_handler


def test_get_celery_config_uses_settings_fallbacks(monkeypatch):
    monkeypatch.setattr(
        config_module,
        "settings",
        SimpleNamespace(
            app_name="Chit Fund Platform",
            app_env="development",
            redis_url="redis://cache.local:6379/2",
            redis_max_connections=33,
            redis_health_check_interval_seconds=13,
            redis_socket_connect_timeout_seconds=2.0,
            redis_socket_timeout_seconds=4.0,
            celery_task_serializer="json",
            celery_result_serializer="json",
            celery_task_ignore_result=False,
            celery_task_store_errors_even_if_ignored=True,
            celery_broker_pool_limit=9,
            celery_auto_close_interval_seconds=75,
            celery_pending_notification_interval_seconds=90,
            payment_reminder_hour_ist=8,
            notification_cleanup_hour_ist=1,
            job_run_cleanup_hour_ist=4,
            read_notification_retention_days=21,
            job_run_retention_days=10,
        ),
    )

    config = get_celery_config()

    assert config["broker_url"] == "redis://cache.local:6379/2"
    assert config["result_backend"] == "redis://cache.local:6379/2"
    assert config["task_serializer"] == "json"
    assert config["accept_content"] == ["json"]
    assert config["result_serializer"] == "json"
    assert config["timezone"] == "Asia/Calcutta"
    assert config["enable_utc"] is True
    assert config["broker_pool_limit"] == 9
    assert config["broker_transport_options"] == {
        "health_check_interval": 13,
        "retry_on_timeout": True,
        "socket_connect_timeout": 2.0,
        "socket_keepalive": True,
        "socket_timeout": 4.0,
        "max_connections": 33,
    }
    assert config["result_backend_transport_options"] == config["broker_transport_options"]


def test_build_celery_app_uses_configured_urls(monkeypatch):
    monkeypatch.setattr(
        config_module,
        "settings",
        SimpleNamespace(
            app_name="Worker Test App",
            app_env="production",
            redis_url="redis://cache.local:6379/2",
            celery_broker_url="redis://broker.local:6379/5",
            celery_result_backend="redis://result.local:6379/6",
            redis_max_connections=None,
            redis_health_check_interval_seconds=30,
            redis_socket_connect_timeout_seconds=5.0,
            redis_socket_timeout_seconds=5.0,
            celery_task_always_eager=True,
            celery_task_serializer="json",
            celery_result_serializer="json",
            celery_task_ignore_result=False,
            celery_task_store_errors_even_if_ignored=True,
            celery_broker_pool_limit=10,
            celery_auto_close_interval_seconds=75,
            celery_pending_notification_interval_seconds=90,
            payment_reminder_hour_ist=8,
            notification_cleanup_hour_ist=1,
            job_run_cleanup_hour_ist=4,
            read_notification_retention_days=21,
            job_run_retention_days=10,
        ),
    )

    celery_app = build_celery_app()

    assert celery_app.main == "Worker Test App"
    assert celery_app.conf.broker_url == "redis://broker.local:6379/5"
    assert celery_app.conf.result_backend == "redis://result.local:6379/6"
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.broker_pool_limit == 10
    assert celery_app.conf.broker_transport_options["retry_on_timeout"] is True
    assert "app.tasks.system_tasks" in celery_app.conf.include
    assert "app.tasks.notification_tasks" in celery_app.conf.include
    assert "app.tasks.auction_tasks" in celery_app.conf.include
    assert celery_app.conf.beat_schedule["auctions-auto-close-expired-sessions"]["schedule"] == 75
    assert celery_app.conf.beat_schedule["notifications-deliver-pending"]["schedule"] == 90
    assert celery_app.conf.beat_schedule["notifications-cleanup-read"]["args"] == (21, 500)
    assert celery_app.conf.beat_schedule["system-cleanup-job-runs"]["args"] == (10, 500)


def test_worker_process_init_handler_bootstraps_database(monkeypatch):
    calls = []

    monkeypatch.setattr("app.core.celery_app.bootstrap_database", lambda: calls.append("bootstrapped"))

    worker_process_init_handler(sender=None)

    assert calls == ["bootstrapped"]
