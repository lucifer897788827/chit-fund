from __future__ import annotations

import logging
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.bootstrap import build_runtime_readiness_report
from app.core.security import CurrentUser, require_admin
from app.core.time import utcnow
from app.models.auction import FinalizeJob
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import Payment, Payout
from app.models.support import AdminMessage
from app.models.user import Owner, Subscriber, User
from app.modules.admin.schemas import AdminMessageCreate
from app.tasks.auction_tasks import get_finalize_job_worker_health

logger = logging.getLogger(__name__)


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


def _serialize_admin_message(message: AdminMessage) -> dict:
    return {
        "id": message.id,
        "message": message.message,
        "type": message.type,
        "active": message.active,
        "createdByUserId": message.created_by_user_id,
        "createdAt": message.created_at,
        "updatedAt": message.updated_at,
    }


def get_active_admin_message(db: Session, current_user: CurrentUser) -> dict | None:
    message = db.scalar(
        select(AdminMessage)
        .where(AdminMessage.active.is_(True))
        .order_by(AdminMessage.created_at.desc(), AdminMessage.id.desc())
        .limit(1)
    )
    return _serialize_admin_message(message) if message is not None else None


def create_admin_message(db: Session, payload: AdminMessageCreate, current_user: CurrentUser) -> dict:
    admin = require_admin(current_user)
    if payload.active:
        for existing_message in db.scalars(select(AdminMessage).where(AdminMessage.active.is_(True))).all():
            existing_message.active = False
            existing_message.updated_at = utcnow()
    message = AdminMessage(
        message=payload.message.strip(),
        type=payload.type,
        active=payload.active,
        created_by_user_id=admin.id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _serialize_admin_message(message)


def _build_admin_user_summary(db: Session, user: User) -> dict:
    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    total_paid = 0
    payment_count = 0
    total_received = 0
    payout_count = 0
    membership_count = 0
    if subscriber is not None:
        payment_count, total_paid = db.execute(
            select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.subscriber_id == subscriber.id
            )
        ).one()
        payout_count, total_received = db.execute(
            select(func.count(Payout.id), func.coalesce(func.sum(Payout.net_amount), 0)).where(
                Payout.subscriber_id == subscriber.id
            )
        ).one()
        membership_count = db.scalar(
            select(func.count(GroupMembership.id)).where(GroupMembership.subscriber_id == subscriber.id)
        ) or 0
    owned_group_count = 0
    if owner is not None:
        owned_group_count = db.scalar(select(func.count(ChitGroup.id)).where(ChitGroup.owner_id == owner.id)) or 0
    return {
        "id": user.id,
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
        "isActive": user.is_active,
        "ownerId": owner.id if owner is not None else None,
        "subscriberId": subscriber.id if subscriber is not None else None,
        "paymentBehavior": {
            "paymentCount": int(payment_count or 0),
            "totalPaid": int(total_paid or 0),
            "payoutCount": int(payout_count or 0),
            "totalReceived": int(total_received or 0),
        },
        "stats": {
            "memberships": int(membership_count or 0),
            "ownedGroups": int(owned_group_count or 0),
        },
    }


def list_admin_users(db: Session, current_user: CurrentUser) -> list[dict]:
    admin = require_admin(current_user)
    started_at = perf_counter()
    query_started_at = perf_counter()
    users = db.scalars(select(User).order_by(User.id.asc())).all()
    db_query_ms = round((perf_counter() - query_started_at) * 1000, 2)
    processing_started_at = perf_counter()
    summaries = [_build_admin_user_summary(db, user) for user in users]
    processing_ms = round((perf_counter() - processing_started_at) * 1000, 2)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "admin.performance",
        extra={
            "event": "admin.performance",
            "endpoint": "/api/admin/users",
            "user_id": admin.id,
            "db_query_ms": db_query_ms,
            "processing_ms": processing_ms,
            "duration_ms": duration_ms,
        },
    )
    return summaries


def get_admin_user(db: Session, user_id: int, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _build_admin_user_summary(db, user)
