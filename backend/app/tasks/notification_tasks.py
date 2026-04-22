from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import date
from time import perf_counter
from typing import Any

from sqlalchemy import select

from app.core import database
from app.core.logging import APP_LOGGER_NAME, log_job_event
from app.models.job_tracking import JobRun
from app.models.support import Notification
from app.modules.notifications.delivery_service import (
    NotificationDeliveryRetryableError,
    deliver_notification,
    deliver_pending_notifications,
    mark_notification_failed,
)
from app.modules.notifications.service import (
    dispatch_staged_notifications,
    notify_payment_reminders,
    prune_read_notifications,
)
from app.modules.support.service import complete_job_run, fail_job_run, start_job_run
from app.tasks.retry_utils import RetryPolicy, retry_operation
from app.tasks.system_tasks import celery_system_task


logger = logging.getLogger(APP_LOGGER_NAME)

NOTIFICATION_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay_seconds=0.25,
    backoff_multiplier=2.0,
    max_delay_seconds=2.0,
)


@dataclass
class _FallbackJobRun:
    id: int = 0


def _current_task_id() -> str | None:
    try:
        from celery import current_task
    except Exception:
        return None

    request = getattr(current_task, "request", None)
    return getattr(request, "id", None)


def _update_job_run(job_run_id: int, *, summary: dict[str, Any], failed: bool = False) -> None:
    if job_run_id <= 0:
        return
    with database.SessionLocal() as db:
        job_run = db.get(JobRun, job_run_id)
        if job_run is None:
            return
        if failed:
            fail_job_run(db, job_run=job_run, summary=summary)
        else:
            complete_job_run(db, job_run=job_run, summary=summary)


def _finalize_failed_delivery(
    db,
    notification_id: int,
    exc: BaseException,
) -> dict[str, Any]:
    failed = mark_notification_failed(db, notification_id)
    return {
        "notificationId": notification_id,
        "status": "failed",
        "channel": failed.channel if failed is not None else None,
        "error": str(exc),
        "sentAt": failed.sent_at if failed is not None else None,
    }


@celery_system_task("notifications.deliver_notification")
def queue_notification_delivery(notification_id: int) -> dict[str, Any]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"notification_id": notification_id}
    try:
        with database.SessionLocal() as tracking_db:
            owner_id = tracking_db.scalar(
                select(Notification.owner_id).where(Notification.id == notification_id)
            )
            job_run = start_job_run(
                tracking_db,
                task_name="notifications.deliver_notification",
                task_id=task_id,
                owner_id=owner_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="notifications.deliver_notification",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    with database.SessionLocal() as db:
        try:
            result = retry_operation(
                lambda: deliver_notification(db, notification_id),
                policy=NOTIFICATION_RETRY_POLICY,
                retryable_exceptions=(NotificationDeliveryRetryableError,),
                on_exhausted=lambda exc: _finalize_failed_delivery(db, notification_id, exc),
            )
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="notifications.deliver_notification",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _update_job_run(job_run.id, summary=metadata | {"error": "delivery_failed"}, failed=True)
            raise

        if result.get("status") == "failed":
            log_job_event(
                logger,
                event="job.failure",
                job_name="notifications.deliver_notification",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata | {"result_status": result.get("status")},
                level=logging.ERROR,
            )
            _update_job_run(job_run.id, summary=metadata | result, failed=True)
            return result

    log_job_event(
        logger,
        event="job.success",
        job_name="notifications.deliver_notification",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_status": result.get("status")},
    )
    _update_job_run(job_run.id, summary=metadata | result)
    return result


@celery_system_task("notifications.deliver_pending_notifications")
def queue_pending_notification_deliveries(limit: int = 100) -> list[dict[str, Any]]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"limit": limit}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="notifications.deliver_pending_notifications",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="notifications.deliver_pending_notifications",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    with database.SessionLocal() as db:
        try:
            results = deliver_pending_notifications(db, limit=limit)
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="notifications.deliver_pending_notifications",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _update_job_run(job_run.id, summary=metadata | {"error": "deliver_pending_failed"}, failed=True)
            raise

    log_job_event(
        logger,
        event="job.success",
        job_name="notifications.deliver_pending_notifications",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_count": len(results)},
    )
    _update_job_run(job_run.id, summary=metadata | {"resultCount": len(results)})
    return results


@celery_system_task("notifications.queue_payment_reminders")
def queue_payment_reminders(as_of: str | None = None) -> list[dict[str, Any]]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"as_of": as_of}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="notifications.queue_payment_reminders",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="notifications.queue_payment_reminders",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    reminder_date = date.fromisoformat(as_of) if as_of else None
    with database.SessionLocal() as db:
        try:
            notifications = notify_payment_reminders(db, as_of=reminder_date)
            db.commit()
            dispatch_staged_notifications(db)
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="notifications.queue_payment_reminders",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _update_job_run(job_run.id, summary=metadata | {"error": "payment_reminders_failed"}, failed=True)
            raise

    log_job_event(
        logger,
        event="job.success",
        job_name="notifications.queue_payment_reminders",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_count": len(notifications)},
    )
    _update_job_run(job_run.id, summary=metadata | {"resultCount": len(notifications)})
    return [
        {
            "notificationId": notification.id,
            "userId": notification.user_id,
            "ownerId": notification.owner_id,
            "channel": notification.channel,
            "title": notification.title,
        }
        for notification in notifications
    ]


@celery_system_task("notifications.cleanup_read_notifications")
def queue_cleanup_read_notifications(older_than_days: int = 30, limit: int = 500) -> dict[str, int]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"older_than_days": older_than_days, "limit": limit}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="notifications.cleanup_read_notifications",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="notifications.cleanup_read_notifications",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    with database.SessionLocal() as db:
        try:
            result = prune_read_notifications(db, older_than_days=older_than_days, limit=limit)
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="notifications.cleanup_read_notifications",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _update_job_run(job_run.id, summary=metadata | {"error": "cleanup_read_notifications_failed"}, failed=True)
            raise

    log_job_event(
        logger,
        event="job.success",
        job_name="notifications.cleanup_read_notifications",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_count": result.get("deletedCount")},
    )
    _update_job_run(job_run.id, summary=metadata | result)
    return result
