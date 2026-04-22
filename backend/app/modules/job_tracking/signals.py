from __future__ import annotations

from typing import Any

from celery.signals import task_failure, task_prerun, task_success
from fastapi.encoders import jsonable_encoder

from app.core import database
from app.modules.job_tracking.service import record_job_failed, record_job_started, record_job_succeeded


def _task_name(sender: Any) -> str | None:
    return getattr(sender, "name", None) if sender is not None else None


def _task_summary(args: tuple[Any, ...] | None, kwargs: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "arguments": {
            "argCount": len(args or ()),
            "kwargKeys": sorted((kwargs or {}).keys()),
        }
    }


@task_prerun.connect(weak=False)
def task_started_handler(sender=None, task_id=None, args=None, kwargs=None, **_ignored):
    task_name = _task_name(sender)
    if not task_name or not task_id:
        return

    with database.SessionLocal() as db:
        record_job_started(
            db,
            task_name=task_name,
            task_id=task_id,
            summary=_task_summary(args, kwargs),
        )


@task_success.connect(weak=False)
def task_succeeded_handler(sender=None, result=None, task_id=None, **_ignored):
    task_name = _task_name(sender)
    if not task_name or not task_id:
        return

    with database.SessionLocal() as db:
        record_job_succeeded(
            db,
            task_name=task_name,
            task_id=task_id,
            summary={"result": jsonable_encoder(result)},
        )


@task_failure.connect(weak=False)
def task_failed_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_ignored):
    task_name = _task_name(sender)
    if not task_name or not task_id:
        return

    with database.SessionLocal() as db:
        record_job_failed(
            db,
            task_name=task_name,
            task_id=task_id,
            summary={
                "error": str(exception),
                "errorType": exception.__class__.__name__ if exception is not None else "Exception",
                "arguments": _task_summary(args, kwargs)["arguments"],
            },
        )

