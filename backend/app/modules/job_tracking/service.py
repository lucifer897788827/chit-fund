from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner
from app.core.time import utcnow
from app.models.job_tracking import JobRun


def _dump_summary(summary: dict[str, Any] | None) -> str | None:
    if summary is None:
        return None

    return json.dumps(summary, default=str, separators=(",", ":"))


def _load_summary(summary_json: str | None) -> dict[str, Any] | None:
    if not summary_json:
        return None

    try:
        value = json.loads(summary_json)
    except json.JSONDecodeError:
        return {"raw": summary_json}

    return value if isinstance(value, dict) else {"value": value}


def _merge_summary(existing_summary: str | None, patch: dict[str, Any] | None) -> str | None:
    if patch is None:
        return existing_summary

    summary = _load_summary(existing_summary) or {}
    summary.update(patch)
    return _dump_summary(summary)


def _get_job_run(db: Session, task_id: str | None) -> JobRun | None:
    if not task_id:
        return None

    return db.scalar(select(JobRun).where(JobRun.task_id == task_id))


def start_job_run(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    now = utcnow()
    job_run = _get_job_run(db, task_id)

    if job_run is None:
        job_run = JobRun(
            owner_id=owner_id,
            task_name=task_name,
            task_id=task_id,
            status="running",
            attempts=1,
            started_at=now,
            summary_json=_dump_summary(summary),
        )
        db.add(job_run)
    else:
        job_run.owner_id = owner_id
        job_run.task_name = task_name
        job_run.status = "running"
        job_run.attempts = (job_run.attempts or 0) + 1
        job_run.started_at = job_run.started_at or now
        job_run.completed_at = None
        job_run.failed_at = None
        job_run.summary_json = _merge_summary(job_run.summary_json, summary)

    db.commit()
    db.refresh(job_run)
    return job_run


def complete_job_run(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    now = utcnow()
    job_run = _get_job_run(db, task_id)

    if job_run is None:
        job_run = JobRun(
            owner_id=owner_id,
            task_name=task_name,
            task_id=task_id,
            status="completed",
            attempts=1,
            started_at=now,
            completed_at=now,
            summary_json=_dump_summary(summary),
        )
        db.add(job_run)
    else:
        job_run.owner_id = owner_id if owner_id is not None else job_run.owner_id
        job_run.task_name = task_name
        job_run.status = "completed"
        job_run.completed_at = now
        job_run.failed_at = None
        job_run.summary_json = _merge_summary(job_run.summary_json, summary)

    db.commit()
    db.refresh(job_run)
    return job_run


def fail_job_run(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    now = utcnow()
    job_run = _get_job_run(db, task_id)

    if job_run is None:
        job_run = JobRun(
            owner_id=owner_id,
            task_name=task_name,
            task_id=task_id,
            status="failed",
            attempts=1,
            started_at=now,
            failed_at=now,
            summary_json=_dump_summary(summary),
        )
        db.add(job_run)
    else:
        job_run.owner_id = owner_id if owner_id is not None else job_run.owner_id
        job_run.task_name = task_name
        job_run.status = "failed"
        job_run.failed_at = now
        job_run.completed_at = None
        job_run.summary_json = _merge_summary(job_run.summary_json, summary)

    db.commit()
    db.refresh(job_run)
    return job_run


def list_job_runs(
    db: Session,
    current_user: CurrentUser | None = None,
    *,
    task_name: str | None = None,
    status: str | None = None,
    limit: int = 25,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict[str, Any]] | PaginatedResponse[dict[str, Any]]:
    query = select(JobRun).order_by(JobRun.started_at.desc().nullslast(), JobRun.id.desc())
    if current_user is not None:
        owner = require_owner(current_user)
        query = query.where(JobRun.owner_id == owner.id)
    normalized_limit = max(1, min(int(limit), 200))

    if task_name:
        query = query.where(JobRun.task_name == task_name)
    if status:
        query = query.where(JobRun.status == status)

    pagination = resolve_pagination(page, page_size, default_page_size=normalized_limit)
    if pagination is None:
        job_runs = db.scalars(query.limit(normalized_limit)).all()
        return [serialize_job_run(job_run) for job_run in job_runs]

    total_count = count_statement(db, query)
    job_runs = db.scalars(apply_pagination(query, pagination)).all()
    return build_paginated_response([serialize_job_run(job_run) for job_run in job_runs], pagination, total_count)


def get_job_run(db: Session, job_run_id: int) -> JobRun | None:
    return db.scalar(select(JobRun).where(JobRun.id == job_run_id))


def serialize_job_run(job_run: JobRun) -> dict[str, Any]:
    return {
        "id": job_run.id,
        "ownerId": job_run.owner_id,
        "jobType": job_run.task_name,
        "taskId": job_run.task_id,
        "status": job_run.status,
        "attempts": job_run.attempts,
        "startedAt": job_run.started_at,
        "completedAt": job_run.completed_at,
        "failedAt": job_run.failed_at,
        "summary": _load_summary(job_run.summary_json),
        "createdAt": job_run.created_at,
        "updatedAt": job_run.updated_at,
    }


def record_job_started(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    return start_job_run(db, task_name=task_name, task_id=task_id, owner_id=owner_id, summary=summary)


def record_job_succeeded(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    return complete_job_run(db, task_name=task_name, task_id=task_id, owner_id=owner_id, summary=summary)


def record_job_failed(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    return fail_job_run(db, task_name=task_name, task_id=task_id, owner_id=owner_id, summary=summary)
