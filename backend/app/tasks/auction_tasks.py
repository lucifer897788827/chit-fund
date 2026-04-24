from __future__ import annotations

from dataclasses import dataclass
import logging
import sys
from time import perf_counter
from threading import Thread
from threading import Lock
from types import SimpleNamespace
from typing import Any

from app.core import database
from app.core.logging import APP_LOGGER_NAME, log_job_event
from app.core.time import utcnow
from app.models.job_tracking import JobRun
from app.modules.auctions.service import (
    ensure_finalize_job_enqueued,
    finalize_expired_open_auction_sessions,
    process_pending_finalize_jobs as process_pending_finalize_jobs_from_db,
    reconcile_incomplete_auctions,
)
from app.modules.support.service import complete_job_run, fail_job_run, start_job_run
from app.tasks.system_tasks import celery_app as system_celery_app
from app.tasks.system_tasks import celery_system_task


logger = logging.getLogger(APP_LOGGER_NAME)
_FINALIZE_WORKER_STATE_LOCK = Lock()
_FINALIZE_WORKER_STATE: dict[str, Any] = {
    "status": "idle",
    "lastDispatchMode": None,
    "lastDispatchAt": None,
    "lastRunStartedAt": None,
    "lastRunFinishedAt": None,
    "lastSuccessAt": None,
    "lastProcessedCount": 0,
    "lastError": None,
}


@dataclass
class _FallbackJobRun:
    id: int = 0


def _update_finalize_worker_state(**fields: Any) -> dict[str, Any]:
    with _FINALIZE_WORKER_STATE_LOCK:
        _FINALIZE_WORKER_STATE.update(fields)
        return dict(_FINALIZE_WORKER_STATE)


def get_finalize_job_worker_health() -> dict[str, Any]:
    with _FINALIZE_WORKER_STATE_LOCK:
        return dict(_FINALIZE_WORKER_STATE)


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


def get_db_session():
    return database.SessionLocal()


def _execute_finalize_post_processing_task(session_id: int) -> dict[str, Any]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"session_id": int(session_id)}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="auctions.finalize_post_processing",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="auctions.finalize_post_processing",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    db = get_db_session()
    try:
        ensure_finalize_job_enqueued(db, int(session_id))
        db.commit()
        processed_jobs = process_pending_finalize_jobs_from_db(
            db,
            auction_id=int(session_id),
            limit=1,
        )
        result = processed_jobs[0] if processed_jobs else {"sessionId": int(session_id), "processed": False}
    except Exception:
        log_job_event(
            logger,
            event="job.failure",
            job_name="auctions.finalize_post_processing",
            status="failed",
            task_id=task_id,
            duration_ms=(perf_counter() - started_at) * 1000,
            metadata=metadata,
            level=logging.ERROR,
            exc_info=True,
        )
        _update_job_run(job_run.id, summary=metadata | {"error": "finalize_post_processing_failed"}, failed=True)
        raise
    finally:
        db.close()

    log_job_event(
        logger,
        event="job.success",
        job_name="auctions.finalize_post_processing",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | result,
    )
    _update_job_run(job_run.id, summary=metadata | result)
    return result


if system_celery_app is not None:

    @system_celery_app.task(
        name="auctions.finalize_post_processing",
        bind=True,
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_kwargs={"max_retries": 5},
    )
    def finalize_post_processing(self, session_id: int) -> dict[str, Any]:
        return _execute_finalize_post_processing_task(session_id)

else:

    class _FinalizePostProcessingTask:
        name = "auctions.finalize_post_processing"
        request = SimpleNamespace(retries=0)

        def __call__(self, session_id: int) -> dict[str, Any]:
            return _execute_finalize_post_processing_task(session_id)

        def delay(self, session_id: int) -> dict[str, Any]:
            if "pytest" in sys.modules:
                return _execute_finalize_post_processing_task(int(session_id))
            thread = Thread(
                target=_execute_finalize_post_processing_task,
                args=(int(session_id),),
                daemon=True,
            )
            thread.start()
            return {"status": "queued", "sessionId": int(session_id)}

        def apply_async(
            self,
            args: tuple[Any, ...] | None = None,
            kwargs: dict[str, Any] | None = None,
            **_ignored: Any,
        ) -> dict[str, Any]:
            session_id = int((args or ())[0] if args else (kwargs or {}).get("session_id"))
            return self.delay(session_id)

    finalize_post_processing = _FinalizePostProcessingTask()


queue_finalize_post_processing = finalize_post_processing


def _run_pending_finalize_recovery_scan(
    *,
    limit: int | None = None,
    auction_id: int | None = None,
    reason: str = "manual",
) -> list[dict[str, Any]]:
    logger.info(
        "recovery scan started",
        extra={
            "event": "auction.finalize.recovery_scan.started",
            "reason": reason,
            "limit": limit,
            "auction_id": auction_id,
        },
    )
    processed = run_finalize_job_worker_cycle(limit=limit, auction_id=auction_id)
    logger.info(
        "recovery scan completed",
        extra={
            "event": "auction.finalize.recovery_scan.completed",
            "reason": reason,
            "limit": limit,
            "auction_id": auction_id,
            "processed_count": len(processed),
        },
    )
    return processed


def process_pending_finalize_jobs(
    limit: int | None = None,
    *,
    auction_id: int | None = None,
    reason: str = "manual",
) -> dict[str, Any]:
    if "pytest" in sys.modules:
        processed = _run_pending_finalize_recovery_scan(
            limit=limit,
            auction_id=auction_id,
            reason=reason,
        )
        return {
            "status": "completed",
            "processedCount": len(processed),
            "processedJobs": processed,
        }

    Thread(
        target=_run_pending_finalize_recovery_scan,
        kwargs={
            "limit": limit,
            "auction_id": auction_id,
            "reason": reason,
        },
        daemon=True,
        name="auction-finalize-recovery-scan",
    ).start()
    return {
        "status": "started",
        "reason": reason,
        "limit": limit,
        "auctionId": auction_id,
    }


def run_finalize_job_worker_cycle(
    *,
    limit: int | None = None,
    auction_id: int | None = None,
) -> list[dict[str, Any]]:
    _update_finalize_worker_state(
        status="running",
        lastRunStartedAt=utcnow().isoformat(),
    )
    with database.SessionLocal() as db:
        try:
            processed = process_pending_finalize_jobs_from_db(
                db,
                limit=limit,
                auction_id=auction_id,
            )
        except Exception as exc:
            _update_finalize_worker_state(
                status="failed",
                lastRunFinishedAt=utcnow().isoformat(),
                lastError=str(exc),
            )
            raise
    _update_finalize_worker_state(
        status="ready" if processed else "idle",
        lastRunFinishedAt=utcnow().isoformat(),
        lastSuccessAt=utcnow().isoformat(),
        lastProcessedCount=len(processed),
        lastError=None,
    )
    return processed


@celery_system_task("auctions.process_finalize_jobs")
def queue_process_finalize_jobs(limit: int | None = None) -> dict[str, Any]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"limit": limit}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="auctions.process_finalize_jobs",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="auctions.process_finalize_jobs",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    try:
        processed = run_finalize_job_worker_cycle(limit=limit)
        result = {
            "processedCount": len(processed),
            "processedJobs": processed,
        }
    except Exception:
        log_job_event(
            logger,
            event="job.failure",
            job_name="auctions.process_finalize_jobs",
            status="failed",
            task_id=task_id,
            duration_ms=(perf_counter() - started_at) * 1000,
            metadata=metadata,
            level=logging.ERROR,
            exc_info=True,
        )
        _update_job_run(job_run.id, summary=metadata | {"error": "process_finalize_jobs_failed"}, failed=True)
        raise

    log_job_event(
        logger,
        event="job.success",
        job_name="auctions.process_finalize_jobs",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | {"processedCount": result["processedCount"]},
    )
    _update_job_run(job_run.id, summary=metadata | result)
    return result


def _run_finalize_job_worker_locally(limit: int | None = None) -> None:
    try:
        queue_process_finalize_jobs(limit=limit)
    except Exception:
        logger.exception(
            "Finalize job worker thread failed",
            extra={
                "event": "auction.finalize.worker.thread_failed",
            },
        )


def wake_finalize_job_worker(limit: int | None = None) -> str:
    if system_celery_app is not None:
        try:
            queue_process_finalize_jobs.apply_async(
                kwargs={"limit": limit},
                ignore_result=True,
                retry=False,
            )
            _update_finalize_worker_state(
                lastDispatchMode="celery",
                lastDispatchAt=utcnow().isoformat(),
                lastError=None,
            )
            logger.info(
                "Finalize worker dispatched via Celery",
                extra={
                    "event": "auction.finalize.worker.dispatched",
                    "dispatch_mode": "celery",
                    "limit": limit,
                },
            )
            return "celery"
        except Exception:
            logger.exception(
                "Finalize job worker enqueue failed; falling back to thread",
                extra={
                    "event": "auction.finalize.worker.enqueue_failed",
                },
            )

    Thread(
        target=_run_finalize_job_worker_locally,
        kwargs={"limit": limit},
        daemon=True,
        name="auction-finalize-worker",
    ).start()
    _update_finalize_worker_state(
        lastDispatchMode="thread",
        lastDispatchAt=utcnow().isoformat(),
        lastError=None,
    )
    logger.info(
        "Finalize worker dispatched via thread",
        extra={
            "event": "auction.finalize.worker.dispatched",
            "dispatch_mode": "thread",
            "limit": limit,
        },
    )
    return "thread"


@celery_system_task("auctions.reconcile_incomplete_auctions")
def queue_reconcile_incomplete_auctions(limit: int | None = None) -> dict[str, Any]:
    task_id = _current_task_id()
    started_at = perf_counter()
    metadata = {"limit": limit}
    try:
        with database.SessionLocal() as tracking_db:
            job_run = start_job_run(
                tracking_db,
                task_name="auctions.reconcile_incomplete_auctions",
                task_id=task_id,
                summary=metadata,
            )
    except Exception:
        job_run = _FallbackJobRun()

    log_job_event(
        logger,
        event="job.start",
        job_name="auctions.reconcile_incomplete_auctions",
        status="started",
        task_id=task_id,
        metadata=metadata,
    )
    try:
        with database.SessionLocal() as db:
            result = reconcile_incomplete_auctions(db, limit=limit)
    except Exception:
        log_job_event(
            logger,
            event="job.failure",
            job_name="auctions.reconcile_incomplete_auctions",
            status="failed",
            task_id=task_id,
            duration_ms=(perf_counter() - started_at) * 1000,
            metadata=metadata,
            level=logging.ERROR,
            exc_info=True,
        )
        _update_job_run(job_run.id, summary=metadata | {"error": "reconcile_incomplete_auctions_failed"}, failed=True)
        raise

    log_job_event(
        logger,
        event="job.success",
        job_name="auctions.reconcile_incomplete_auctions",
        status="success",
        task_id=task_id,
        duration_ms=(perf_counter() - started_at) * 1000,
        metadata=metadata | result,
    )
    _update_job_run(job_run.id, summary=metadata | result)
    return result


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
