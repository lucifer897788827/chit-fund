from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_ready

from app.core.bootstrap import bootstrap_database
from app.core import config as config_module
from app.core.logging import APP_LOGGER_NAME

DEFAULT_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_RESULT_BACKEND = "redis://localhost:6379/0"
logger = logging.getLogger(APP_LOGGER_NAME)


def _setting_value(name: str, default: Any = None) -> Any:
    value = getattr(config_module.settings, name, None)
    if value not in (None, ""):
        return value

    env_name = name.upper()
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value

    return default


def _setting_bool(name: str, default: bool = False) -> bool:
    value = _setting_value(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def get_celery_config() -> dict[str, Any]:
    broker_url = _setting_value("celery_broker_url", _setting_value("redis_url", DEFAULT_BROKER_URL))
    result_backend = _setting_value("celery_result_backend", broker_url or DEFAULT_RESULT_BACKEND)
    app_name = _setting_value("celery_app_name", _setting_value("app_name", "chit_fund_worker"))
    app_env = str(_setting_value("app_env", "production")).lower()
    task_always_eager = _setting_bool("celery_task_always_eager", False)
    redis_transport_options: dict[str, Any] = {
        "health_check_interval": int(_setting_value("redis_health_check_interval_seconds", 30)),
        "retry_on_timeout": True,
        "socket_connect_timeout": float(_setting_value("redis_socket_connect_timeout_seconds", 5.0)),
        "socket_keepalive": True,
        "socket_timeout": float(_setting_value("redis_socket_timeout_seconds", 5.0)),
    }
    redis_max_connections = _setting_value("redis_max_connections", None)
    if redis_max_connections not in (None, ""):
        redis_transport_options["max_connections"] = int(redis_max_connections)

    return {
        "broker_url": broker_url,
        "result_backend": result_backend,
        "task_serializer": _setting_value("celery_task_serializer", "json"),
        "accept_content": [_setting_value("celery_task_serializer", "json")],
        "result_serializer": _setting_value("celery_result_serializer", "json"),
        "task_ignore_result": _setting_bool("celery_task_ignore_result", False),
        "task_store_errors_even_if_ignored": _setting_bool("celery_task_store_errors_even_if_ignored", True),
        "timezone": _setting_value("celery_timezone", "Asia/Calcutta"),
        "enable_utc": True,
        "task_track_started": True,
        "worker_prefetch_multiplier": 1,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "worker_hijack_root_logger": False,
        "task_always_eager": task_always_eager,
        "broker_pool_limit": int(_setting_value("celery_broker_pool_limit", 10)),
        "task_soft_time_limit": int(_setting_value("finalize_job_time_limit_seconds", 60)),
        "task_time_limit": int(max(int(_setting_value("finalize_job_time_limit_seconds", 60)) + 15, 30)),
        "broker_transport_options": redis_transport_options,
        "result_backend_transport_options": dict(redis_transport_options),
        "app_name": app_name,
        "app_env": app_env,
    }


def build_celery_app() -> Celery:
    config = get_celery_config()
    celery_app = Celery(
        config["app_name"],
        include=[
            "app.tasks.system_tasks",
            "app.tasks.notification_tasks",
            "app.tasks.auction_tasks",
        ],
    )
    celery_app.conf.update({key: value for key, value in config.items() if key not in {"app_name", "app_env"}})
    celery_app.conf.task_default_queue = _setting_value("celery_default_queue", "default")
    celery_app.conf.task_default_exchange = _setting_value("celery_default_exchange", "default")
    celery_app.conf.task_default_routing_key = _setting_value("celery_default_routing_key", "default")
    celery_app.conf.worker_state_db = _setting_value("celery_worker_state_db", None)
    celery_app.conf.beat_schedule = {
        "auctions-process-finalize-jobs": {
            "task": "auctions.process_finalize_jobs",
            "schedule": 30,
        },
        "auctions-reconcile-incomplete-auctions": {
            "task": "auctions.reconcile_incomplete_auctions",
            "schedule": max(60, int(_setting_value("celery_reconcile_incomplete_auctions_interval_seconds", 300))),
        },
        "auctions-auto-close-expired-sessions": {
            "task": "auctions.auto_close_expired_sessions",
            "schedule": max(30, int(_setting_value("celery_auto_close_interval_seconds", 60))),
        },
        "notifications-deliver-pending": {
            "task": "notifications.deliver_pending_notifications",
            "schedule": max(30, int(_setting_value("celery_pending_notification_interval_seconds", 60))),
        },
        "notifications-payment-reminders": {
            "task": "notifications.queue_payment_reminders",
            "schedule": crontab(
                minute=0,
                hour=int(_setting_value("payment_reminder_hour_ist", 9)),
            ),
        },
        "notifications-cleanup-read": {
            "task": "notifications.cleanup_read_notifications",
            "schedule": crontab(
                minute=0,
                hour=int(_setting_value("notification_cleanup_hour_ist", 2)),
            ),
            "args": (int(_setting_value("read_notification_retention_days", 30)), 500),
        },
        "system-cleanup-job-runs": {
            "task": "system.cleanup_job_runs",
            "schedule": crontab(
                minute=30,
                hour=int(_setting_value("job_run_cleanup_hour_ist", 3)),
            ),
            "args": (int(_setting_value("job_run_retention_days", 14)), 500),
        },
    }
    return celery_app


celery_app = build_celery_app()

from app.modules.job_tracking import signals as _job_tracking_signals  # noqa: F401


@worker_process_init.connect(weak=False)
def worker_process_init_handler(sender: Any = None, **kwargs: Any) -> None:
    logger.info(
        "worker.bootstrap.starting",
        extra={"event": "worker.bootstrap.starting"},
    )
    try:
        bootstrap_database()
    except Exception:
        logger.exception(
            "worker.bootstrap.failed",
            extra={"event": "worker.bootstrap.failed"},
        )
        raise
    logger.info(
        "worker.bootstrap.ready",
        extra={"event": "worker.bootstrap.ready"},
    )


@worker_ready.connect(weak=False)
def process_pending_on_start(sender: Any = None, **kwargs: Any) -> None:
    logger.info(
        "Finalize worker startup recovery triggered",
        extra={"event": "auction.finalize.recovery_scan.startup_triggered"},
    )
    try:
        from app.tasks.auction_tasks import process_pending_finalize_jobs

        process_pending_finalize_jobs(reason="worker_ready")
    except Exception:
        logger.exception(
            "Finalize worker startup recovery failed to start",
            extra={"event": "auction.finalize.recovery_scan.startup_failed"},
        )
