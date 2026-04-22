from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any

from app.core import database
from app.core.logging import APP_LOGGER_NAME, log_job_event
from app.models.job_tracking import JobRun
from app.modules.auctions.service import finalize_expired_open_auction_sessions
from app.modules.support.service import complete_job_run, fail_job_run, start_job_run
from app.tasks.system_tasks import celery_system_task


logger = logging.getLogger(APP_LOGGER_NAME)


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


@celery_system_task("auctions.auto_close_expired_sessions")
def queue_expired_auction_auto_close(limit: int | None = None) -> list[dict[str, Any]]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"limit": limit}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="auctions.auto_close_expired_sessions",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="auctions.auto_close_expired_sessions",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    with database.SessionLocal() as db:
        try:
            result = finalize_expired_open_auction_sessions(db, limit=limit)
        except Exception:
            log_job_event(
                logger,
                event="job.failure",
                job_name="auctions.auto_close_expired_sessions",
                status="failed",
                task_id=task_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                metadata=metadata,
                level=logging.ERROR,
                exc_info=True,
            )
            _update_job_run(job_run.id, summary=metadata | {"error": "auto_close_failed"}, failed=True)
            raise

    log_job_event(
        logger,
        event="job.success",
        job_name="auctions.auto_close_expired_sessions",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"result_count": len(result)},
    )
    _update_job_run(job_run.id, summary=metadata | {"resultCount": len(result)})
    return result
