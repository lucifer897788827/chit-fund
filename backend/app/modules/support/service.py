from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner
from app.core.time import utcnow
from app.models.job_tracking import JobRun


def _encode_summary(summary: dict[str, Any] | None) -> str | None:
    if summary is None:
        return None
    return json.dumps(summary, separators=(",", ":"), default=str)


def _decode_summary(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def start_job_run(
    db: Session,
    *,
    task_name: str,
    task_id: str | None,
    owner_id: int | None = None,
    summary: dict[str, Any] | None = None,
) -> JobRun:
    job_run = db.scalar(select(JobRun).where(JobRun.task_id == task_id)) if task_id else None
    now = utcnow()
    if job_run is None:
        job_run = JobRun(
            owner_id=owner_id,
            task_name=task_name,
            task_id=task_id,
            status="running",
            attempts=1,
            started_at=now,
            completed_at=None,
            failed_at=None,
            summary_json=_encode_summary(summary),
        )
        db.add(job_run)
    else:
        job_run.owner_id = owner_id
        job_run.status = "running"
        job_run.attempts += 1
        job_run.started_at = now
        job_run.completed_at = None
        job_run.failed_at = None
        job_run.summary_json = _encode_summary(summary)
        job_run.updated_at = now

    db.commit()
    db.refresh(job_run)
    return job_run


def complete_job_run(db: Session, *, job_run: JobRun, summary: dict[str, Any] | None = None) -> JobRun:
    job_run.status = "success"
    job_run.completed_at = utcnow()
    job_run.failed_at = None
    if summary is not None:
        job_run.summary_json = _encode_summary(summary)
    db.commit()
    db.refresh(job_run)
    return job_run


def fail_job_run(db: Session, *, job_run: JobRun, summary: dict[str, Any] | None = None) -> JobRun:
    job_run.status = "failed"
    job_run.failed_at = utcnow()
    if summary is not None:
        job_run.summary_json = _encode_summary(summary)
    db.commit()
    db.refresh(job_run)
    return job_run


def serialize_job_run(job_run: JobRun) -> dict[str, Any]:
    return {
        "id": job_run.id,
        "ownerId": job_run.owner_id,
        "taskName": job_run.task_name,
        "taskId": job_run.task_id,
        "status": job_run.status,
        "attempts": job_run.attempts,
        "startedAt": job_run.started_at,
        "completedAt": job_run.completed_at,
        "failedAt": job_run.failed_at,
        "summary": _decode_summary(job_run.summary_json),
        "createdAt": job_run.created_at,
        "updatedAt": job_run.updated_at,
    }


def list_job_runs(
    db: Session,
    current_user: CurrentUser,
    *,
    status: str | None = None,
    task_name: str | None = None,
    limit: int = 50,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict[str, Any]] | PaginatedResponse[dict[str, Any]]:
    owner = require_owner(current_user)
    query = select(JobRun).order_by(JobRun.created_at.desc(), JobRun.id.desc())
    query = query.where(JobRun.owner_id == owner.id)
    if status:
        query = query.where(JobRun.status == status)
    if task_name:
        query = query.where(JobRun.task_name == task_name)
    pagination = resolve_pagination(page, page_size, default_page_size=limit)
    if pagination is None:
        return [serialize_job_run(row) for row in db.scalars(query.limit(max(1, min(limit, 200)))).all()]

    total_count = count_statement(db, query)
    rows = db.scalars(apply_pagination(query, pagination)).all()
    return build_paginated_response([serialize_job_run(row) for row in rows], pagination, total_count)


def prune_job_runs(
    db: Session,
    *,
    older_than_days: int = 14,
    limit: int = 500,
) -> dict[str, int]:
    cutoff_at = utcnow() - timedelta(days=older_than_days)
    stale_job_ids = db.scalars(
        select(JobRun.id)
        .where(
            JobRun.status.in_(("success", "failed")),
            or_(
                and_(JobRun.completed_at.is_not(None), JobRun.completed_at < cutoff_at),
                and_(JobRun.failed_at.is_not(None), JobRun.failed_at < cutoff_at),
            ),
        )
        .order_by(JobRun.updated_at.asc(), JobRun.id.asc())
        .limit(limit)
    ).all()
    if not stale_job_ids:
        return {
            "deletedCount": 0,
            "cutoffDays": older_than_days,
        }

    db.execute(delete(JobRun).where(JobRun.id.in_(stale_job_ids)))
    db.commit()
    return {
        "deletedCount": len(stale_job_ids),
        "cutoffDays": older_than_days,
    }
