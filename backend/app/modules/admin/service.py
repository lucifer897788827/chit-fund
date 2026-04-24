from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.bootstrap import build_runtime_readiness_report
from app.core.security import CurrentUser, require_admin
from app.models.auction import FinalizeJob
from app.tasks.auction_tasks import get_finalize_job_worker_health


def list_finalize_jobs(db: Session, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    status_counts = {
        status: count
        for status, count in db.execute(
            select(FinalizeJob.status, func.count(FinalizeJob.id))
            .group_by(FinalizeJob.status)
            .order_by(FinalizeJob.status.asc())
        ).all()
    }
    jobs = db.scalars(
        select(FinalizeJob)
        .order_by(FinalizeJob.created_at.desc(), FinalizeJob.id.desc())
        .limit(100)
    ).all()
    return {
        "counts": {
            "pending": int(status_counts.get("pending", 0) or 0),
            "processing": int(status_counts.get("processing", 0) or 0),
            "done": int(status_counts.get("done", 0) or 0),
            "failed": int(status_counts.get("failed", 0) or 0),
        },
        "jobs": [
            {
                "id": job.id,
                "auctionId": job.auction_id,
                "status": job.status,
                "retryCount": int(job.retry_count or 0),
                "lastError": job.last_error,
                "createdAt": job.created_at,
                "updatedAt": job.updated_at,
            }
            for job in jobs
        ],
    }


def build_admin_system_health(db: Session, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    readiness = build_runtime_readiness_report()
    backlog = {
        status: int(count or 0)
        for status, count in db.execute(
            select(FinalizeJob.status, func.count(FinalizeJob.id))
            .group_by(FinalizeJob.status)
        ).all()
    }
    return {
        "database": readiness["checks"]["database"],
        "worker": get_finalize_job_worker_health(),
        "queueBacklog": {
            "pending": backlog.get("pending", 0),
            "processing": backlog.get("processing", 0),
            "failed": backlog.get("failed", 0),
            "done": backlog.get("done", 0),
        },
        "readiness": readiness,
    }
