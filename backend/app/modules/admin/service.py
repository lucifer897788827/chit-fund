from __future__ import annotations

import logging
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.bootstrap import build_runtime_readiness_report
from app.core.pagination import apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_admin
from app.core.time import utcnow
from app.models.auction import AuctionBid, AuctionResult, AuctionSession, FinalizeJob
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.external import ExternalChit
from app.models.money import Payment, Payout
from app.models.support import AdminMessage
from app.models.user import Owner, Subscriber, User
from app.modules.admin.cache import (
    invalidate_admin_users_cache,
    load_admin_user_detail_cache,
    load_admin_users_cache,
    store_admin_user_detail_cache,
    store_admin_users_cache,
)
from app.modules.admin.schemas import AdminMessageCreate
from app.tasks.auction_tasks import get_finalize_job_worker_health

logger = logging.getLogger(__name__)


def _get_admin_target_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _assert_admin_deactivation_allowed(target_user: User, acting_admin: User) -> None:
    if target_user.id == acting_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot deactivate themselves",
        )
    if target_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin users cannot be deactivated",
        )


def _assert_admin_activation_allowed(target_user: User, acting_admin: User) -> None:
    if target_user.id == acting_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot activate themselves",
        )
    if target_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin users cannot be activated",
        )


def _apply_user_deactivation(db: Session, target_user: User) -> None:
    target_user.is_active = False
    target_user.updated_at = utcnow()

    owner_profile = db.scalar(select(Owner).where(Owner.user_id == target_user.id))
    if owner_profile is not None:
        owner_profile.status = "inactive"

    subscriber_profile = db.scalar(select(Subscriber).where(Subscriber.user_id == target_user.id))
    if subscriber_profile is not None:
        subscriber_profile.status = "inactive"


def _apply_user_activation(db: Session, target_user: User) -> None:
    target_user.is_active = True
    target_user.updated_at = utcnow()

    owner_profile = db.scalar(select(Owner).where(Owner.user_id == target_user.id))
    if owner_profile is not None:
        owner_profile.status = "active"

    subscriber_profile = db.scalar(select(Subscriber).where(Subscriber.user_id == target_user.id))
    if subscriber_profile is not None:
        subscriber_profile.status = "active"


def deactivate_admin_user(db: Session, user_id: int, current_user: CurrentUser) -> dict:
    admin = require_admin(current_user)
    target_user = _get_admin_target_user(db, user_id)
    _assert_admin_deactivation_allowed(target_user, admin)
    _apply_user_deactivation(db, target_user)
    db.commit()
    invalidate_admin_users_cache()
    return {
        "id": target_user.id,
        "isActive": bool(target_user.is_active),
    }


def activate_admin_user(db: Session, user_id: int, current_user: CurrentUser) -> dict:
    admin = require_admin(current_user)
    target_user = _get_admin_target_user(db, user_id)
    _assert_admin_activation_allowed(target_user, admin)
    _apply_user_activation(db, target_user)
    db.commit()
    invalidate_admin_users_cache()
    return {
        "id": target_user.id,
        "isActive": bool(target_user.is_active),
    }


def bulk_deactivate_admin_users(db: Session, user_ids: list[int], current_user: CurrentUser) -> dict:
    admin = require_admin(current_user)
    normalized_user_ids = list(dict.fromkeys(user_ids))
    target_users = db.scalars(select(User).where(User.id.in_(normalized_user_ids))).all()
    target_users_by_id = {user.id: user for user in target_users}
    missing_user_ids = [user_id for user_id in normalized_user_ids if user_id not in target_users_by_id]
    if missing_user_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for user_id in normalized_user_ids:
        _assert_admin_deactivation_allowed(target_users_by_id[user_id], admin)

    for user_id in normalized_user_ids:
        _apply_user_deactivation(db, target_users_by_id[user_id])

    db.commit()
    invalidate_admin_users_cache()
    return {
        "deactivatedUserIds": normalized_user_ids,
        "count": len(normalized_user_ids),
    }


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


def _normalize_admin_search_term(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def list_admin_groups(db: Session, current_user: CurrentUser, *, status: str | None = None, search: str | None = None) -> list[dict]:
    require_admin(current_user)
    normalized_status = (status or "").strip().lower() or None
    normalized_search = _normalize_admin_search_term(search)

    statement = (
        select(
            ChitGroup.id.label("id"),
            ChitGroup.title.label("title"),
            ChitGroup.status.label("status"),
            func.coalesce(Owner.display_name, Owner.business_name, User.phone).label("owner_name"),
            func.count(GroupMembership.id).label("members_count"),
            ChitGroup.installment_amount.label("monthly_amount"),
        )
        .join(Owner, Owner.id == ChitGroup.owner_id)
        .join(User, User.id == Owner.user_id)
        .outerjoin(GroupMembership, GroupMembership.group_id == ChitGroup.id)
        .group_by(
            ChitGroup.id,
            ChitGroup.title,
            ChitGroup.status,
            Owner.display_name,
            Owner.business_name,
            User.phone,
            ChitGroup.installment_amount,
        )
        .order_by(ChitGroup.created_at.desc(), ChitGroup.id.desc())
    )
    if normalized_status:
        statement = statement.where(func.lower(ChitGroup.status) == normalized_status)
    if normalized_search:
        search_pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                func.lower(ChitGroup.title).like(search_pattern),
                func.lower(func.coalesce(Owner.display_name, Owner.business_name, User.phone)).like(search_pattern),
            )
        )

    rows = db.execute(statement).all()

    return [
        {
            "id": row.id,
            "name": row.title,
            "status": row.status,
            "owner": row.owner_name,
            "membersCount": int(row.members_count or 0),
            "monthlyAmount": int(row.monthly_amount or 0),
        }
        for row in rows
    ]


def _serialize_admin_group_month(value) -> str:
    if value is None:
        return "N/A"
    try:
        return value.strftime("%b %Y")
    except AttributeError:
        return str(value)


def get_admin_group(db: Session, group_id: int, current_user: CurrentUser) -> dict:
    require_admin(current_user)

    group_row = db.execute(
        select(
            ChitGroup.id.label("id"),
            ChitGroup.title.label("title"),
            ChitGroup.status.label("status"),
            ChitGroup.installment_amount.label("monthly_amount"),
            ChitGroup.chit_value.label("chit_value"),
            ChitGroup.current_cycle_no.label("current_cycle_no"),
            ChitGroup.start_date.label("start_date"),
            ChitGroup.first_auction_date.label("first_auction_date"),
            func.coalesce(Owner.display_name, Owner.business_name, User.phone).label("owner_name"),
            User.phone.label("owner_phone"),
            func.count(GroupMembership.id).label("members_count"),
        )
        .join(Owner, Owner.id == ChitGroup.owner_id)
        .join(User, User.id == Owner.user_id)
        .outerjoin(GroupMembership, GroupMembership.group_id == ChitGroup.id)
        .where(ChitGroup.id == group_id)
        .group_by(
            ChitGroup.id,
            ChitGroup.title,
            ChitGroup.status,
            ChitGroup.installment_amount,
            ChitGroup.chit_value,
            ChitGroup.current_cycle_no,
            ChitGroup.start_date,
            ChitGroup.first_auction_date,
            Owner.display_name,
            Owner.business_name,
            User.phone,
        )
    ).first()
    if group_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    payments_sq = (
        select(
            Payment.membership_id.label("membership_id"),
            func.count(Payment.id).label("payment_count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total_paid"),
        )
        .where(Payment.membership_id.is_not(None))
        .group_by(Payment.membership_id)
        .subquery()
    )
    payouts_sq = (
        select(
            Payout.membership_id.label("membership_id"),
            func.count(Payout.id).label("payout_count"),
            func.coalesce(func.sum(Payout.net_amount), 0).label("total_received"),
        )
        .group_by(Payout.membership_id)
        .subquery()
    )
    installments_sq = (
        select(
            Installment.membership_id.label("membership_id"),
            func.count(Installment.id).label("total_installments"),
            func.sum(
                case(
                    (((Installment.status == "paid") | (Installment.balance_amount <= 0)), 1),
                    else_=0,
                )
            ).label("paid_installments"),
            func.sum(case((func.coalesce(Installment.balance_amount, 0) > 0, 1), else_=0)).label("pending_installments"),
            func.coalesce(func.sum(Installment.balance_amount), 0).label("pending_amount"),
        )
        .group_by(Installment.membership_id)
        .subquery()
    )

    member_rows = db.execute(
        select(
            GroupMembership.id.label("membership_id"),
            User.id.label("user_id"),
            func.coalesce(Subscriber.full_name, User.phone).label("display_name"),
            User.phone.label("phone"),
            GroupMembership.membership_status.label("membership_status"),
            GroupMembership.prized_status.label("prized_status"),
            func.coalesce(payments_sq.c.total_paid, 0).label("total_paid"),
            func.coalesce(payouts_sq.c.total_received, 0).label("total_received"),
            func.coalesce(installments_sq.c.total_installments, 0).label("total_installments"),
            func.coalesce(installments_sq.c.paid_installments, 0).label("paid_installments"),
            func.coalesce(installments_sq.c.pending_installments, 0).label("pending_installments"),
            func.coalesce(installments_sq.c.pending_amount, 0).label("pending_amount"),
        )
        .join(Subscriber, Subscriber.id == GroupMembership.subscriber_id)
        .join(User, User.id == Subscriber.user_id)
        .outerjoin(payments_sq, payments_sq.c.membership_id == GroupMembership.id)
        .outerjoin(payouts_sq, payouts_sq.c.membership_id == GroupMembership.id)
        .outerjoin(installments_sq, installments_sq.c.membership_id == GroupMembership.id)
        .where(GroupMembership.group_id == group_id)
        .order_by(GroupMembership.member_no.asc(), GroupMembership.id.asc())
    ).all()

    members = []
    defaulters = []
    for row in member_rows:
        total_paid = int(row.total_paid or 0)
        total_received = int(row.total_received or 0)
        payment_score = _payment_score(
            paid_installments=int(row.paid_installments or 0),
            total_installments=int(row.total_installments or 0),
        )
        member_payload = {
            "membershipId": row.membership_id,
            "userId": row.user_id,
            "name": row.display_name,
            "phone": row.phone,
            "membershipStatus": row.membership_status,
            "prizedStatus": row.prized_status,
            "totalPaid": total_paid,
            "totalReceived": total_received,
            "netPosition": total_received - total_paid,
            "paymentScore": payment_score,
            "pendingPaymentsCount": int(row.pending_installments or 0),
            "pendingAmount": int(row.pending_amount or 0),
        }
        members.append(member_payload)
        if member_payload["pendingPaymentsCount"] > 1:
            defaulters.append(
                {
                    "userId": member_payload["userId"],
                    "name": member_payload["name"],
                    "phone": member_payload["phone"],
                    "pendingPaymentsCount": member_payload["pendingPaymentsCount"],
                    "pendingAmount": member_payload["pendingAmount"],
                    "paymentScore": member_payload["paymentScore"],
                    "netPosition": member_payload["netPosition"],
                }
            )

    total_collected = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(GroupMembership, GroupMembership.id == Payment.membership_id)
        .where(GroupMembership.group_id == group_id)
    ) or 0
    total_paid_out = db.scalar(
        select(func.coalesce(func.sum(Payout.net_amount), 0))
        .where(Payout.membership_id.in_(select(GroupMembership.id).where(GroupMembership.group_id == group_id)))
    ) or 0
    pending_amount = db.scalar(
        select(func.coalesce(func.sum(Installment.balance_amount), 0)).where(Installment.group_id == group_id)
    ) or 0

    winner_name_sq = (
        select(Subscriber.full_name)
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .where(GroupMembership.id == AuctionResult.winner_membership_id)
        .scalar_subquery()
    )
    auction_rows = db.execute(
        select(
            AuctionSession.id.label("id"),
            AuctionSession.cycle_no.label("cycle_no"),
            AuctionSession.scheduled_start_at.label("scheduled_at"),
            AuctionSession.status.label("status"),
            winner_name_sq.label("winner_name"),
            AuctionResult.winning_bid_amount.label("winning_bid_amount"),
        )
        .outerjoin(AuctionResult, AuctionResult.auction_session_id == AuctionSession.id)
        .where(AuctionSession.group_id == group_id)
        .order_by(AuctionSession.cycle_no.desc(), AuctionSession.id.desc())
    ).all()
    auctions = [
        {
            "id": row.id,
            "cycleNo": int(row.cycle_no or 0),
            "month": _serialize_admin_group_month(row.scheduled_at),
            "winner": row.winner_name,
            "bidAmount": int(row.winning_bid_amount) if row.winning_bid_amount is not None else None,
            "status": row.status,
            "scheduledAt": row.scheduled_at,
        }
        for row in auction_rows
    ]

    return {
        "group": {
            "id": group_row.id,
            "name": group_row.title,
            "status": group_row.status,
            "owner": group_row.owner_name,
            "ownerPhone": group_row.owner_phone,
            "membersCount": int(group_row.members_count or 0),
            "monthlyAmount": int(group_row.monthly_amount or 0),
            "chitValue": int(group_row.chit_value or 0),
            "currentCycleNo": int(group_row.current_cycle_no or 0),
            "startDate": group_row.start_date,
            "firstAuctionDate": group_row.first_auction_date,
        },
        "members": members,
        "financialSummary": {
            "totalCollected": int(total_collected or 0),
            "totalPaid": int(total_paid_out or 0),
            "pendingAmount": int(pending_amount or 0),
        },
        "auctions": auctions,
        "defaulters": defaulters,
    }


def list_admin_auctions(db: Session, current_user: CurrentUser) -> list[dict]:
    require_admin(current_user)
    winner_name_sq = (
        select(Subscriber.full_name)
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .where(GroupMembership.id == AuctionResult.winner_membership_id)
        .scalar_subquery()
    )

    latest_bid_amount_sq = (
        select(AuctionBid.bid_amount)
        .where(AuctionBid.auction_session_id == AuctionSession.id)
        .order_by(AuctionBid.bid_amount.desc(), AuctionBid.placed_at.desc(), AuctionBid.id.desc())
        .limit(1)
        .scalar_subquery()
    )

    rows = db.execute(
        select(
            AuctionSession.id.label("id"),
            ChitGroup.title.label("group_title"),
            AuctionSession.status.label("status"),
            AuctionSession.scheduled_start_at.label("scheduled_start_at"),
            winner_name_sq.label("winner_name"),
            func.coalesce(AuctionResult.winning_bid_amount, latest_bid_amount_sq).label("bid_amount"),
        )
        .join(ChitGroup, ChitGroup.id == AuctionSession.group_id)
        .outerjoin(AuctionResult, AuctionResult.auction_session_id == AuctionSession.id)
        .order_by(AuctionSession.created_at.desc(), AuctionSession.id.desc())
    ).all()

    return [
        {
            "id": row.id,
            "group": row.group_title,
            "winner": row.winner_name,
            "bidAmount": int(row.bid_amount) if row.bid_amount is not None else None,
            "status": row.status,
            "scheduledAt": row.scheduled_start_at,
        }
        for row in rows
    ]


def _normalize_admin_payment_status(status_value: str | None) -> str:
    normalized = (status_value or "").strip().lower()
    if normalized in {"pending", "due", "scheduled"}:
        return "pending"
    return "paid"


def list_admin_payments(db: Session, current_user: CurrentUser, *, status: str | None = None, search: str | None = None) -> list[dict]:
    require_admin(current_user)
    normalized_status = (status or "").strip().lower() or None
    normalized_search = _normalize_admin_search_term(search)

    statement = (
        select(
            Payment.id.label("id"),
            Payment.amount.label("amount"),
            Payment.status.label("status"),
            Subscriber.full_name.label("subscriber_name"),
            User.phone.label("subscriber_phone"),
            ChitGroup.title.label("group_title"),
            ChitGroup.id.label("group_id"),
        )
        .join(Subscriber, Subscriber.id == Payment.subscriber_id)
        .join(User, User.id == Subscriber.user_id)
        .outerjoin(GroupMembership, GroupMembership.id == Payment.membership_id)
        .outerjoin(Installment, Installment.id == Payment.installment_id)
        .outerjoin(
            ChitGroup,
            ChitGroup.id == func.coalesce(GroupMembership.group_id, Installment.group_id),
        )
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    )
    if normalized_status:
        pending_statuses = ["pending", "due", "scheduled"]
        if normalized_status == "pending":
            statement = statement.where(func.lower(Payment.status).in_(pending_statuses))
        elif normalized_status == "paid":
            statement = statement.where(~func.lower(Payment.status).in_(pending_statuses))
    if normalized_search:
        search_pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                func.lower(func.coalesce(Subscriber.full_name, User.phone)).like(search_pattern),
                func.lower(User.phone).like(search_pattern),
                func.lower(func.coalesce(ChitGroup.title, "")).like(search_pattern),
            )
        )

    rows = db.execute(statement).all()

    return [
        {
            "id": row.id,
            "user": row.subscriber_name or row.subscriber_phone,
            "group": row.group_title,
            "groupId": row.group_id,
            "amount": int(row.amount or 0),
            "status": _normalize_admin_payment_status(row.status),
        }
        for row in rows
    ]


def list_admin_defaulters(db: Session, current_user: CurrentUser, *, threshold: int = 1) -> list[dict]:
    require_admin(current_user)
    display_name = func.coalesce(Subscriber.full_name, Owner.display_name, Owner.business_name, User.phone)
    pending_count = func.count(Installment.id)
    pending_amount = func.coalesce(func.sum(Installment.balance_amount), 0)

    rows = db.execute(
        select(
            User.id.label("user_id"),
            display_name.label("display_name"),
            User.phone.label("phone"),
            pending_count.label("pending_count"),
            pending_amount.label("pending_amount"),
        )
        .join(Subscriber, Subscriber.user_id == User.id)
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .join(Installment, Installment.membership_id == GroupMembership.id)
        .outerjoin(Owner, Owner.user_id == User.id)
        .where(
            func.coalesce(Installment.balance_amount, 0) > 0,
            func.lower(Installment.status) != "paid",
        )
        .group_by(User.id, Subscriber.full_name, Owner.display_name, Owner.business_name, User.phone)
        .having(pending_count > max(int(threshold or 0), 0))
        .order_by(pending_count.desc(), pending_amount.desc(), User.id.asc())
    ).all()

    return [
        {
            "userId": row.user_id,
            "name": row.display_name,
            "phone": row.phone,
            "pendingPaymentsCount": int(row.pending_count or 0),
            "pendingAmount": int(row.pending_amount or 0),
        }
        for row in rows
    ]


def list_admin_summary(db: Session, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    pending_statuses = ["pending", "due", "scheduled"]

    total_users = db.scalar(select(func.count(User.id))) or 0
    active_groups = db.scalar(
        select(func.count(ChitGroup.id)).where(func.lower(ChitGroup.status) == "active")
    ) or 0
    pending_payments = db.scalar(
        select(func.count(Payment.id)).where(func.lower(Payment.status).in_(pending_statuses))
    ) or 0

    defaulter_groups = (
        select(User.id.label("user_id"))
        .join(Subscriber, Subscriber.user_id == User.id)
        .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
        .join(Installment, Installment.membership_id == GroupMembership.id)
        .where(
            func.coalesce(Installment.balance_amount, 0) > 0,
            func.lower(Installment.status) != "paid",
        )
        .group_by(User.id)
        .having(func.count(Installment.id) > 1)
        .subquery()
    )
    defaulters = db.scalar(select(func.count()).select_from(defaulter_groups)) or 0

    return {
        "totalUsers": int(total_users),
        "activeGroups": int(active_groups),
        "pendingPayments": int(pending_payments),
        "defaulters": int(defaulters),
    }


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


def _admin_user_list_statement(
    *,
    lite: bool,
    role: str | None = None,
    active: bool | None = None,
    search: str | None = None,
    score_range: str | None = None,
):
    owned_chits_sq = _owned_chits_subquery()
    joined_chits_sq = _joined_chits_subquery(include_membership_stats=False)
    external_chits_sq = _external_chits_subquery()
    installments_sq = None if lite and not score_range else _installments_subquery()
    display_name = func.coalesce(Owner.display_name, Owner.business_name, Subscriber.full_name, User.phone)

    selected_columns = [
        User.id.label("id"),
        User.phone.label("phone"),
        User.role.label("role"),
        User.is_active.label("is_active"),
        User.created_at.label("created_at"),
        Owner.id.label("owner_id"),
        Subscriber.id.label("subscriber_id"),
        display_name.label("display_name"),
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

    normalized_role = (role or "").strip().lower() or None
    if normalized_role == "owner":
        statement = statement.where(Owner.id.is_not(None))
    elif normalized_role == "subscriber":
        statement = statement.where(Subscriber.id.is_not(None))
    elif normalized_role == "admin":
        statement = statement.where(User.role == "admin")

    if active is not None:
        statement = statement.where(User.is_active.is_(active))

    normalized_search = _normalize_admin_search_term(search)
    if normalized_search:
        search_pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                func.lower(User.phone).like(search_pattern),
                func.lower(display_name).like(search_pattern),
            )
        )

    normalized_score_range = (score_range or "").strip().lower() or None
    if normalized_score_range and installments_sq is not None:
        total_installments = func.coalesce(installments_sq.c.total_installments, 0)
        paid_installments = func.coalesce(installments_sq.c.paid_installments, 0)
        payment_score = case(
            (total_installments <= 0, 0),
            else_=(paid_installments * 100.0) / total_installments,
        )
        if normalized_score_range == "high":
            statement = statement.where(payment_score >= 80)
        elif normalized_score_range == "medium":
            statement = statement.where(payment_score >= 50, payment_score < 80)
        elif normalized_score_range == "low":
            statement = statement.where(payment_score < 50)

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
        "name": row.display_name,
        "phone": row.phone,
        "isActive": bool(row.is_active),
        "createdAt": row.created_at,
        "totalChits": total_chits,
        "paymentScore": _payment_score(
            paid_installments=int(row.paid_installments or 0),
            total_installments=int(row.total_installments or 0),
        ),
    }


def _load_admin_user_chits(db: Session, row) -> list[dict]:
    chits: list[dict] = []

    if row.owner_id is not None:
        owned_groups = db.scalars(
            select(ChitGroup)
            .where(ChitGroup.owner_id == row.owner_id)
            .order_by(ChitGroup.created_at.desc(), ChitGroup.id.desc())
        ).all()
        chits.extend(
            {
                "id": group.id,
                "kind": "owned",
                "groupCode": group.group_code,
                "title": group.title,
                "status": group.status,
                "currentCycleNo": int(group.current_cycle_no or 0),
            }
            for group in owned_groups
        )

    if row.subscriber_id is not None:
        joined_groups = db.execute(
            select(ChitGroup)
            .join(GroupMembership, GroupMembership.group_id == ChitGroup.id)
            .where(GroupMembership.subscriber_id == row.subscriber_id)
            .order_by(ChitGroup.created_at.desc(), ChitGroup.id.desc())
        ).scalars().all()
        chits.extend(
            {
                "id": group.id,
                "kind": "joined",
                "groupCode": group.group_code,
                "title": group.title,
                "status": group.status,
                "currentCycleNo": int(group.current_cycle_no or 0),
            }
            for group in joined_groups
        )

    return chits


def _load_admin_user_payments(db: Session, row) -> list[dict]:
    if row.subscriber_id is None:
        return []

    payments = db.scalars(
        select(Payment)
        .where(Payment.subscriber_id == row.subscriber_id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    ).all()
    return [
        {
            "id": payment.id,
            "amount": int(payment.amount or 0),
            "paymentDate": payment.payment_date,
            "status": payment.status,
            "paymentType": payment.payment_type,
            "paymentMethod": payment.payment_method,
            "groupId": None,
            "membershipId": payment.membership_id,
        }
        for payment in payments
    ]


def _load_admin_user_external_chits(db: Session, row) -> list[dict]:
    if row.subscriber_id is None:
        return []

    external_chits = db.scalars(
        select(ExternalChit)
        .where(ExternalChit.subscriber_id == row.subscriber_id)
        .order_by(ExternalChit.created_at.desc(), ExternalChit.id.desc())
    ).all()
    return [
        {
            "id": chit.id,
            "title": chit.title,
            "organizerName": chit.organizer_name,
            "chitValue": int(chit.chit_value or 0),
            "installmentAmount": int(chit.installment_amount or 0),
            "startDate": chit.start_date,
            "status": chit.status,
        }
        for chit in external_chits
    ]


def _serialize_admin_user_detail(db: Session, row, *, lite: bool) -> dict:
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
    chits = [] if lite else _load_admin_user_chits(db, row)
    payments = [] if lite else _load_admin_user_payments(db, row)
    external_chits = [] if lite else _load_admin_user_external_chits(db, row)

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
            "netPosition": total_received - total_paid,
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
        "chits": chits,
        "payments": payments,
        "externalChitsData": external_chits,
    }


def list_admin_users(
    db: Session,
    current_user: CurrentUser,
    *,
    page: int,
    limit: int,
    lite: bool,
    role: str | None = None,
    active: bool | None = None,
    search: str | None = None,
    score_range: str | None = None,
):
    admin = require_admin(current_user)
    started_at = perf_counter()
    pagination = resolve_pagination(page, limit, default_page_size=20, max_page_size=200)
    assert pagination is not None
    use_cache = role is None and active is None and score_range is None and not _normalize_admin_search_term(search)

    cache_started_at = perf_counter()
    cached_payload = load_admin_users_cache(page, limit, lite) if use_cache else None
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

    statement = _admin_user_list_statement(
        lite=lite,
        role=role,
        active=active,
        search=search,
        score_range=score_range,
    ).order_by(User.created_at.desc(), User.id.desc())
    query_started_at = perf_counter()
    total_count = count_statement(db, statement)
    rows = db.execute(apply_pagination(statement, pagination)).all()
    db_query_ms = round((perf_counter() - query_started_at) * 1000, 2)

    processing_started_at = perf_counter()
    summaries = [_serialize_admin_user_list_item(row) for row in rows]
    processing_ms = round((perf_counter() - processing_started_at) * 1000, 2)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)

    payload = build_paginated_response(summaries, pagination, total_count).model_dump(mode="json")
    if use_cache:
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
    payload = _serialize_admin_user_detail(db, row, lite=lite)
    store_admin_user_detail_cache(user_id, lite, payload)
    return payload
