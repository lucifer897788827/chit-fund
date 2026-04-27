from __future__ import annotations

import logging
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.bootstrap import build_runtime_readiness_report
from app.core.pagination import apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_admin
from app.core.time import utcnow
from app.models.auction import FinalizeJob
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.external import ExternalChit
from app.models.money import Payment, Payout
from app.models.support import AdminMessage
from app.models.user import Owner, Subscriber, User
from app.modules.admin.cache import (
    load_admin_user_detail_cache,
    load_admin_users_cache,
    store_admin_user_detail_cache,
    store_admin_users_cache,
)
from app.modules.admin.schemas import AdminMessageCreate
from app.tasks.auction_tasks import get_finalize_job_worker_health

logger = logging.getLogger(__name__)


def list_finalize_jobs(db: Session, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    status_counts = {
        status_value: count
        for status_value, count in db.execute(
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
        status_value: int(count or 0)
        for status_value, count in db.execute(
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


def _normalized_admin_role(row) -> str:
    if row.role == "admin":
        return "admin"
    if row.owner_id is not None:
        return "owner"
    if row.subscriber_id is not None:
        return "subscriber"
    return row.role


def _payment_score(*, paid_installments: int, total_installments: int) -> int:
    if total_installments <= 0:
        return 0
    return max(0, min(100, round((paid_installments / total_installments) * 100)))


def _owned_chits_subquery():
    return (
        select(
            Owner.user_id.label("user_id"),
            func.count(ChitGroup.id).label("owned_chits"),
        )
        .join(ChitGroup, ChitGroup.owner_id == Owner.id)
        .group_by(Owner.user_id)
        .subquery()
    )


def _joined_chits_subquery(*, include_membership_stats: bool):
    selected_columns = [
        Subscriber.user_id.label("user_id"),
        func.count(func.distinct(GroupMembership.group_id)).label("joined_chits"),
    ]
    if include_membership_stats:
        selected_columns.extend(
            [
                func.count(GroupMembership.id).label("membership_count"),
                func.sum(case((GroupMembership.membership_status == "active", 1), else_=0)).label("active_memberships"),
                func.sum(case((GroupMembership.prized_status == "prized", 1), else_=0)).label("prized_memberships"),
            ]
        )
    return (
        select(*selected_columns)
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .group_by(Subscriber.user_id)
        .subquery()
    )


def _external_chits_subquery():
    return (
        select(
            Subscriber.user_id.label("user_id"),
            func.count(ExternalChit.id).label("external_chits"),
        )
        .join(ExternalChit, ExternalChit.subscriber_id == Subscriber.id)
        .group_by(Subscriber.user_id)
        .subquery()
    )


def _installments_subquery():
    return (
        select(
            Subscriber.user_id.label("user_id"),
            func.count(Installment.id).label("total_installments"),
            func.sum(
                case(
                    (((Installment.status == "paid") | (Installment.balance_amount <= 0)), 1),
                    else_=0,
                )
            ).label("paid_installments"),
        )
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .join(Installment, Installment.membership_id == GroupMembership.id)
        .group_by(Subscriber.user_id)
        .subquery()
    )


def _payments_subquery():
    return (
        select(
            Subscriber.user_id.label("user_id"),
            func.count(Payment.id).label("payment_count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total_paid"),
        )
        .join(Payment, Payment.subscriber_id == Subscriber.id)
        .group_by(Subscriber.user_id)
        .subquery()
    )


def _payouts_subquery():
    return (
        select(
            Subscriber.user_id.label("user_id"),
            func.count(Payout.id).label("payout_count"),
            func.coalesce(func.sum(Payout.net_amount), 0).label("total_received"),
        )
        .join(Payout, Payout.subscriber_id == Subscriber.id)
        .group_by(Subscriber.user_id)
        .subquery()
    )


def _admin_user_list_statement(*, lite: bool):
    owned_chits_sq = _owned_chits_subquery()
    joined_chits_sq = _joined_chits_subquery(include_membership_stats=False)
    external_chits_sq = _external_chits_subquery()
    installments_sq = None if lite else _installments_subquery()

    selected_columns = [
        User.id.label("id"),
        User.phone.label("phone"),
        User.role.label("role"),
        User.created_at.label("created_at"),
        Owner.id.label("owner_id"),
        Subscriber.id.label("subscriber_id"),
        func.coalesce(owned_chits_sq.c.owned_chits, 0).label("owned_chits"),
        func.coalesce(joined_chits_sq.c.joined_chits, 0).label("joined_chits"),
        func.coalesce(external_chits_sq.c.external_chits, 0).label("external_chits"),
    ]
    if lite:
        selected_columns.extend(
            [
                func.cast(0, Installment.id.type).label("total_installments"),
                func.cast(0, Installment.id.type).label("paid_installments"),
            ]
        )
    else:
        selected_columns.extend(
            [
                func.coalesce(installments_sq.c.total_installments, 0).label("total_installments"),
                func.coalesce(installments_sq.c.paid_installments, 0).label("paid_installments"),
            ]
        )

    statement = (
        select(*selected_columns)
        .outerjoin(Owner, Owner.user_id == User.id)
        .outerjoin(Subscriber, Subscriber.user_id == User.id)
        .outerjoin(owned_chits_sq, owned_chits_sq.c.user_id == User.id)
        .outerjoin(joined_chits_sq, joined_chits_sq.c.user_id == User.id)
        .outerjoin(external_chits_sq, external_chits_sq.c.user_id == User.id)
    )
    if installments_sq is not None:
        statement = statement.outerjoin(installments_sq, installments_sq.c.user_id == User.id)
    return statement


def _admin_user_detail_statement():
    owned_chits_sq = _owned_chits_subquery()
    joined_chits_sq = _joined_chits_subquery(include_membership_stats=True)
    external_chits_sq = _external_chits_subquery()
    payments_sq = _payments_subquery()
    payouts_sq = _payouts_subquery()
    installments_sq = _installments_subquery()

    return (
        select(
            User.id.label("id"),
            User.phone.label("phone"),
            User.email.label("email"),
            User.role.label("role"),
            User.is_active.label("is_active"),
            User.created_at.label("created_at"),
            Owner.id.label("owner_id"),
            Subscriber.id.label("subscriber_id"),
            func.coalesce(owned_chits_sq.c.owned_chits, 0).label("owned_chits"),
            func.coalesce(joined_chits_sq.c.joined_chits, 0).label("joined_chits"),
            func.coalesce(external_chits_sq.c.external_chits, 0).label("external_chits"),
            func.coalesce(joined_chits_sq.c.membership_count, 0).label("membership_count"),
            func.coalesce(joined_chits_sq.c.active_memberships, 0).label("active_memberships"),
            func.coalesce(joined_chits_sq.c.prized_memberships, 0).label("prized_memberships"),
            func.coalesce(payments_sq.c.payment_count, 0).label("payment_count"),
            func.coalesce(payments_sq.c.total_paid, 0).label("total_paid"),
            func.coalesce(payouts_sq.c.payout_count, 0).label("payout_count"),
            func.coalesce(payouts_sq.c.total_received, 0).label("total_received"),
            func.coalesce(installments_sq.c.total_installments, 0).label("total_installments"),
            func.coalesce(installments_sq.c.paid_installments, 0).label("paid_installments"),
        )
        .outerjoin(Owner, Owner.user_id == User.id)
        .outerjoin(Subscriber, Subscriber.user_id == User.id)
        .outerjoin(owned_chits_sq, owned_chits_sq.c.user_id == User.id)
        .outerjoin(joined_chits_sq, joined_chits_sq.c.user_id == User.id)
        .outerjoin(external_chits_sq, external_chits_sq.c.user_id == User.id)
        .outerjoin(payments_sq, payments_sq.c.user_id == User.id)
        .outerjoin(payouts_sq, payouts_sq.c.user_id == User.id)
        .outerjoin(installments_sq, installments_sq.c.user_id == User.id)
    )


def _serialize_admin_user_list_item(row) -> dict:
    total_chits = int(row.owned_chits or 0) + int(row.joined_chits or 0) + int(row.external_chits or 0)
    return {
        "id": row.id,
        "role": _normalized_admin_role(row),
        "phone": row.phone,
        "createdAt": row.created_at,
        "totalChits": total_chits,
        "paymentScore": _payment_score(
            paid_installments=int(row.paid_installments or 0),
            total_installments=int(row.total_installments or 0),
        ),
    }


def _serialize_admin_user_detail(row, *, lite: bool) -> dict:
    total_chits = int(row.owned_chits or 0) + int(row.joined_chits or 0) + int(row.external_chits or 0)
    payment_score = _payment_score(
        paid_installments=int(row.paid_installments or 0),
        total_installments=int(row.total_installments or 0),
    )
    total_paid = 0 if lite else int(row.total_paid or 0)
    total_received = 0 if lite else int(row.total_received or 0)
    membership_count = 0 if lite else int(row.membership_count or 0)
    active_memberships = 0 if lite else int(row.active_memberships or 0)
    prized_memberships = 0 if lite else int(row.prized_memberships or 0)
    payment_count = 0 if lite else int(row.payment_count or 0)
    payout_count = 0 if lite else int(row.payout_count or 0)

    return {
        "id": row.id,
        "phone": row.phone,
        "email": row.email,
        "role": _normalized_admin_role(row),
        "createdAt": row.created_at,
        "isActive": bool(row.is_active),
        "ownerId": row.owner_id,
        "subscriberId": row.subscriber_id,
        "financialSummary": {
            "paymentCount": payment_count,
            "totalPaid": total_paid,
            "payoutCount": payout_count,
            "totalReceived": total_received,
            "netCashflow": total_received - total_paid,
            "paymentScore": payment_score,
        },
        "participationStats": {
            "totalChits": total_chits,
            "ownedChits": int(row.owned_chits or 0),
            "joinedChits": int(row.joined_chits or 0),
            "externalChits": int(row.external_chits or 0),
            "membershipCount": membership_count,
            "activeMemberships": active_memberships,
            "prizedMemberships": prized_memberships,
        },
    }


def list_admin_users(db: Session, current_user: CurrentUser, *, page: int, limit: int, lite: bool):
    admin = require_admin(current_user)
    started_at = perf_counter()
    pagination = resolve_pagination(page, limit, default_page_size=20, max_page_size=200)
    assert pagination is not None

    cache_started_at = perf_counter()
    cached_payload = load_admin_users_cache(page, limit, lite)
    cache_lookup_ms = round((perf_counter() - cache_started_at) * 1000, 2)
    if isinstance(cached_payload, dict):
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "ADMIN USERS: cache=hit db=0.00 ms processing=0.00 ms total=%s ms lite=%s",
            duration_ms,
            lite,
            extra={
                "event": "admin.performance",
                "endpoint": "/api/admin/users",
                "user_id": admin.id,
                "cache_hit": True,
                "cache_lookup_ms": cache_lookup_ms,
                "db_query_ms": 0.0,
                "processing_ms": 0.0,
                "duration_ms": duration_ms,
                "lite": lite,
            },
        )
        return cached_payload

    statement = _admin_user_list_statement(lite=lite).order_by(User.created_at.desc(), User.id.desc())
    query_started_at = perf_counter()
    total_count = count_statement(db, statement)
    rows = db.execute(apply_pagination(statement, pagination)).all()
    db_query_ms = round((perf_counter() - query_started_at) * 1000, 2)

    processing_started_at = perf_counter()
    summaries = [_serialize_admin_user_list_item(row) for row in rows]
    processing_ms = round((perf_counter() - processing_started_at) * 1000, 2)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)

    payload = build_paginated_response(summaries, pagination, total_count).model_dump(mode="json")
    store_admin_users_cache(page, limit, lite, payload)

    logger.info(
        "ADMIN USERS: cache=miss db=%s ms processing=%s ms total=%s ms lite=%s",
        db_query_ms,
        processing_ms,
        duration_ms,
        lite,
        extra={
            "event": "admin.performance",
            "endpoint": "/api/admin/users",
            "user_id": admin.id,
            "cache_hit": False,
            "cache_lookup_ms": cache_lookup_ms,
            "db_query_ms": db_query_ms,
            "processing_ms": processing_ms,
            "duration_ms": duration_ms,
            "lite": lite,
        },
    )
    return payload


def get_admin_user(db: Session, user_id: int, current_user: CurrentUser, *, lite: bool = False) -> dict:
    require_admin(current_user)
    cached_payload = load_admin_user_detail_cache(user_id, lite)
    if isinstance(cached_payload, dict):
        return cached_payload

    row = db.execute(_admin_user_detail_statement().where(User.id == user_id)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    payload = _serialize_admin_user_detail(row, lite=lite)
    store_admin_user_detail_cache(user_id, lite, payload)
    return payload
