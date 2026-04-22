from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
import logging
import sys
from time import perf_counter
from typing import Any, TypeVar, cast

from app.core import database
from app.core.logging import APP_LOGGER_NAME, log_job_event
from app.models.job_tracking import JobRun
from app.modules.support.service import complete_job_run, fail_job_run, prune_job_runs, start_job_run

if "pytest" in sys.modules:
    celery_app = None
else:
    try:
        from app.core.celery_app import celery_app
    except ModuleNotFoundError as exc:
        if exc.name != "app.core.celery_app":
            raise
        celery_app = None


TaskFn = TypeVar("TaskFn", bound=Callable[..., Any])
logger = logging.getLogger(APP_LOGGER_NAME)


@dataclass
class _FallbackJobRun:
    id: int = 0


def celery_system_task(name: str, **task_options: Any):
    """Register a task with Celery when available, otherwise keep a safe local callable."""

    def decorator(fn: TaskFn) -> TaskFn:
        if celery_app is not None:
            return cast(TaskFn, celery_app.task(name=name, **task_options)(fn))

        @wraps(fn)
        def direct(*args: Any, **kwargs: Any):
            return fn(*args, **kwargs)

        def delay(*args: Any, **kwargs: Any):
            return fn(*args, **kwargs)

        def apply_async(
            args: tuple[Any, ...] | None = None,
            kwargs: dict[str, Any] | None = None,
            **_ignored: Any,
        ):
            return fn(*(args or ()), **(kwargs or {}))

        setattr(direct, "name", name)
        setattr(direct, "delay", delay)
        setattr(direct, "apply_async", apply_async)
        return cast(TaskFn, direct)

    return decorator


def _current_task_id() -> str | None:
    try:
        from celery import current_task
    except Exception:
        return None

    request = getattr(current_task, "request", None)
    return getattr(request, "id", None)


def _start_tracked_job(task_name: str, task_id: str | None, metadata: dict[str, Any]):
    try:
        with database.SessionLocal() as db:
            return start_job_run(db, task_name=task_name, task_id=task_id, summary=metadata)
    except Exception:
        return _FallbackJobRun()


def _complete_tracked_job(job_run_id: int, summary: dict[str, Any]):
    if job_run_id <= 0:
        return
    with database.SessionLocal() as db:
        job_run = db.get(JobRun, job_run_id)
        if job_run is None:
            return
        complete_job_run(db, job_run=job_run, summary=summary)


def _fail_tracked_job(job_run_id: int, summary: dict[str, Any]):
    if job_run_id <= 0:
        return
    with database.SessionLocal() as db:
        job_run = db.get(JobRun, job_run_id)
        if job_run is None:
            return
        fail_job_run(db, job_run=job_run, summary=summary)


@celery_system_task("system.health_ping")
def queue_health_ping(message: str = "ok") -> dict[str, str]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"message": message}
    job_run = _start_tracked_job("system.health_ping", task_id, metadata)
    log_job_event(
        logger,
        event="job.start",
        job_name="system.health_ping",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    try:
        result = {
            "status": "ok",
            "task": "system.health_ping",
            "message": message,
        }
    except Exception:
        log_job_event(
            logger,
            event="job.failure",
            job_name="system.health_ping",
            status="failed",
            task_id=task_id,
            duration_ms=(perf_counter() - started_at) * 1000,
            metadata=metadata,
            level=logging.ERROR,
            exc_info=True,
        )
        _fail_tracked_job(job_run.id, metadata | {"error": "health_ping_failed"})
        raise

    log_job_event(
        logger,
        event="job.success",
        job_name="system.health_ping",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_status": result["status"]},
    )
    _complete_tracked_job(job_run.id, metadata | {"result_status": result["status"]})
    return result


@celery_system_task("system.notification_placeholder")
def queue_notification_placeholder(
    recipient: str,
    subject: str,
    preview: str | None = None,
) -> dict[str, str]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata: dict[str, Any] = {
        "recipient": recipient,
        "subject": subject,
    }
    if preview is not None:
        metadata["preview"] = preview
    job_run = _start_tracked_job("system.notification_placeholder", task_id, metadata)

    log_job_event(
        logger,
        event="job.start",
        job_name="system.notification_placeholder",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    try:
        payload: dict[str, str] = {
            "status": "queued",
            "task": "system.notification_placeholder",
            "recipient": recipient,
            "subject": subject,
        }
        if preview is not None:
            payload["preview"] = preview
    except Exception:
        log_job_event(
            logger,
            event="job.failure",
            job_name="system.notification_placeholder",
            status="failed",
            task_id=task_id,
            duration_ms=(perf_counter() - started_at) * 1000,
            metadata=metadata,
            level=logging.ERROR,
            exc_info=True,
        )
        _fail_tracked_job(job_run.id, metadata | {"error": "notification_placeholder_failed"})
        raise

    log_job_event(
        logger,
        event="job.success",
        job_name="system.notification_placeholder",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_status": payload["status"]},
    )
    _complete_tracked_job(job_run.id, metadata | {"result_status": payload["status"]})
    return payload


@celery_system_task("system.cleanup_job_runs")
def queue_cleanup_job_runs(older_than_days: int = 14, limit: int = 500) -> dict[str, int]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"older_than_days": older_than_days, "limit": limit}
    job_run = _start_tracked_job("system.cleanup_job_runs", task_id, metadata)
    log_job_event(
        logger,
        event="job.start",
        job_name="system.cleanup_job_runs",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    with database.SessionLocal() as db:
        try:
            result = prune_job_runs(db, older_than_days=older_than_days, limit=limit)
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="system.cleanup_job_runs",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _fail_tracked_job(job_run.id, metadata | {"error": "cleanup_job_runs_failed"})
            raise

    log_job_event(
        logger,
        event="job.success",
        job_name="system.cleanup_job_runs",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"deletedCount": result["deletedCount"]},
    )
    _complete_tracked_job(job_run.id, metadata | result)
    return result
