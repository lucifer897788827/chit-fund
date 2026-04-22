from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.audit import parse_audit_payload
from app.core.money import money_int, money_int_or_none
from app.core.pagination import (
    PaginatedResponse,
    apply_pagination,
    build_paginated_response,
    count_statement,
    resolve_pagination,
)
from app.core.time import utcnow
from app.core.security import CurrentUser, require_owner
from app.models import AuditLog
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payment
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.service import get_auction_state
from app.modules.groups.service import serialize_penalty_value
from app.modules.payments.installment_service import build_membership_dues_snapshot_map
from app.modules.payments.queries import get_member_outstanding_totals, list_payouts

MAX_OWNER_ACTIVITY_LIMIT = 100
MAX_OWNER_AUDIT_LIMIT = 100


def _normalize_limit(limit: int, *, maximum: int) -> int:
    return max(1, min(int(limit), maximum))


def _format_action_label(action: str) -> str:
    return " ".join(
        part.capitalize()
        for part in str(action).replace(".", " ").replace("_", " ").replace("-", " ").split()
    )


def _build_actor_lookup(db: Session, actor_user_ids: list[int]) -> dict[int, dict[str, str | int | None]]:
    if not actor_user_ids:
        return {}

    users = db.scalars(select(User).where(User.id.in_(actor_user_ids))).all()
    owners = db.scalars(select(Owner).where(Owner.user_id.in_(actor_user_ids))).all()
    subscribers = db.scalars(select(Subscriber).where(Subscriber.user_id.in_(actor_user_ids))).all()

    lookup = {
        user.id: {
            "actorId": user.id,
            "actorName": f"User #{user.id}",
            "actorRole": user.role,
        }
        for user in users
    }
    for owner in owners:
        lookup[owner.user_id] = {
            "actorId": owner.user_id,
            "actorName": owner.display_name,
            "actorRole": "owner",
        }
    for subscriber in subscribers:
        lookup.setdefault(
            subscriber.user_id,
            {
                "actorId": subscriber.user_id,
                "actorName": subscriber.full_name,
                "actorRole": "subscriber",
            },
        )
    return lookup


def _serialize_owner_audit_log(
    audit_log: AuditLog,
    *,
    actor_lookup: dict[int, dict[str, str | int | None]],
) -> dict:
    actor = actor_lookup.get(audit_log.actor_user_id or 0, {})
    return {
        "id": audit_log.id,
        "occurredAt": audit_log.created_at,
        "action": audit_log.action,
        "actionLabel": _format_action_label(audit_log.action),
        "entityType": audit_log.entity_type,
        "entityId": audit_log.entity_id,
        "actorId": audit_log.actor_user_id,
        "actorName": actor.get("actorName"),
        "actorRole": actor.get("actorRole"),
        "ownerId": audit_log.owner_id,
        "metadata": parse_audit_payload(audit_log.metadata_json),
        "before": parse_audit_payload(audit_log.before_json),
        "after": parse_audit_payload(audit_log.after_json),
    }


def _owner_groups(db: Session, owner_id: int) -> list[ChitGroup]:
    return db.scalars(
        select(ChitGroup).where(ChitGroup.owner_id == owner_id).order_by(ChitGroup.id.asc())
    ).all()


def _owner_recent_groups(db: Session, owner_id: int, *, limit: int | None = None) -> list[ChitGroup]:
    statement = (
        select(ChitGroup)
        .where(ChitGroup.owner_id == owner_id)
        .order_by(ChitGroup.created_at.desc().nullslast(), ChitGroup.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return db.scalars(statement).all()


def _owner_payment_rows(
    db: Session,
    owner_id: int,
    *,
    limit: int | None = None,
) -> list[tuple[Payment, int | None, str | None, str | None, int | None]]:
    statement = (
        select(
            Payment,
            func.coalesce(GroupMembership.group_id, Installment.group_id).label("group_id"),
            ChitGroup.group_code,
            ChitGroup.title,
            func.coalesce(Payment.membership_id, Installment.membership_id).label("effective_membership_id"),
        )
        .outerjoin(GroupMembership, GroupMembership.id == Payment.membership_id)
        .outerjoin(Installment, Installment.id == Payment.installment_id)
        .outerjoin(
            ChitGroup,
            ChitGroup.id == func.coalesce(GroupMembership.group_id, Installment.group_id),
        )
        .where(Payment.owner_id == owner_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return db.execute(statement).all()


def _owner_session_rows(
    db: Session,
    owner_id: int,
    *,
    limit: int | None = None,
) -> list[AuctionSession]:
    statement = (
        select(AuctionSession)
        .join(ChitGroup, ChitGroup.id == AuctionSession.group_id)
        .where(ChitGroup.owner_id == owner_id)
        .order_by(AuctionSession.created_at.desc(), AuctionSession.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return db.scalars(statement).all()


def _group_lookup(db: Session, group_ids: list[int]) -> dict[int, ChitGroup]:
    if not group_ids:
        return {}
    groups = db.scalars(select(ChitGroup).where(ChitGroup.id.in_(group_ids))).all()
    return {group.id: group for group in groups}


def _group_membership_stats(db: Session, group_ids: list[int]) -> dict[int, dict[str, int]]:
    if not group_ids:
        return {}

    rows = db.execute(
        select(
            GroupMembership.group_id,
            func.count(GroupMembership.id).label("member_count"),
            func.coalesce(
                func.sum(case((GroupMembership.membership_status == "active", 1), else_=0)),
                0,
            ).label("active_member_count"),
        )
        .where(GroupMembership.group_id.in_(group_ids))
        .group_by(GroupMembership.group_id)
    ).all()

    return {
        row.group_id: {
            "memberCount": int(row.member_count),
            "activeMemberCount": int(row.active_member_count),
        }
        for row in rows
    }


def _group_installment_stats(db: Session, group_ids: list[int]) -> dict[int, dict[str, int]]:
    if not group_ids:
        return {}

    membership_rows = db.execute(
        select(GroupMembership.id, GroupMembership.group_id).where(GroupMembership.group_id.in_(group_ids))
    ).all()
    snapshot_map = build_membership_dues_snapshot_map(db, [membership_id for membership_id, _group_id in membership_rows])
    stats_by_group_id = {
        group_id: {
            "totalDue": 0,
            "totalPaid": 0,
            "outstandingAmount": 0,
            "totalPenaltyAmount": 0,
        }
        for group_id in group_ids
    }

    for membership_id, group_id in membership_rows:
        snapshot = snapshot_map.get(membership_id)
        if snapshot is None:
            continue
        stats_by_group_id[group_id]["totalDue"] += money_int(snapshot.total_due)
        stats_by_group_id[group_id]["totalPaid"] += money_int(snapshot.total_paid)
        stats_by_group_id[group_id]["outstandingAmount"] += money_int(snapshot.outstanding_amount)
        stats_by_group_id[group_id]["totalPenaltyAmount"] += money_int(snapshot.penalty_amount)

    return stats_by_group_id


def _group_auction_stats(db: Session, group_ids: list[int]) -> dict[int, dict[str, int]]:
    if not group_ids:
        return {}

    sessions = db.scalars(
        select(AuctionSession).where(AuctionSession.group_id.in_(group_ids))
    ).all()
    if not sessions:
        return {}

    session_ids = [session.id for session in sessions]
    result_session_ids = set(
        db.scalars(
            select(AuctionResult.auction_session_id).where(AuctionResult.auction_session_id.in_(session_ids))
        ).all()
    )
    now = utcnow()
    stats_by_group_id = {
        group_id: {
            "auctionCount": 0,
            "openAuctionCount": 0,
        }
        for group_id in group_ids
    }

    for session in sessions:
        stats = stats_by_group_id.setdefault(
            session.group_id,
            {
                "auctionCount": 0,
                "openAuctionCount": 0,
            },
        )
        stats["auctionCount"] += 1
        if get_auction_state(session, now=now, has_result=session.id in result_session_ids) == "OPEN":
            stats["openAuctionCount"] += 1

    return stats_by_group_id


def _membership_display_lookup(
    db: Session,
    membership_ids: list[int],
) -> dict[int, dict[str, int | str | None]]:
    if not membership_ids:
        return {}

    memberships = db.scalars(select(GroupMembership).where(GroupMembership.id.in_(membership_ids))).all()
    subscriber_ids = [membership.subscriber_id for membership in memberships]
    subscribers = (
        db.scalars(select(Subscriber).where(Subscriber.id.in_(subscriber_ids))).all()
        if subscriber_ids
        else []
    )
    subscriber_names = {
        subscriber.id: subscriber.full_name
        for subscriber in subscribers
    }

    return {
        membership.id: {
            "membershipId": membership.id,
            "membershipNo": membership.member_no,
            "memberName": subscriber_names.get(membership.subscriber_id),
        }
        for membership in memberships
    }


def list_owner_groups(db: Session, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    groups = _owner_groups(db, owner.id)
    group_ids = [group.id for group in groups]
    membership_stats = _group_membership_stats(db, group_ids)
    installment_stats = _group_installment_stats(db, group_ids)
    auction_stats = _group_auction_stats(db, group_ids)

    latest_payment_at_by_group_id: dict[int, object] = {}
    for payment, group_id, _group_code, _group_title, _membership_id in _owner_payment_rows(db, owner.id):
        if group_id is None:
            continue
        latest_payment_at_by_group_id.setdefault(group_id, payment.created_at)

    return [
        {
            "groupId": group.id,
            "groupCode": group.group_code,
            "title": group.title,
            "status": group.status,
            "currentCycleNo": group.current_cycle_no,
            "memberCount": membership_stats.get(group.id, {}).get("memberCount", 0),
            "activeMemberCount": membership_stats.get(group.id, {}).get("activeMemberCount", 0),
            "totalDue": installment_stats.get(group.id, {}).get("totalDue", 0.0),
            "totalPaid": installment_stats.get(group.id, {}).get("totalPaid", 0.0),
            "outstandingAmount": installment_stats.get(group.id, {}).get("outstandingAmount", 0.0),
            "totalPenaltyAmount": installment_stats.get(group.id, {}).get("totalPenaltyAmount", 0.0),
            "penaltyEnabled": group.penalty_enabled,
            "penaltyType": group.penalty_type,
            "penaltyValue": serialize_penalty_value(group.penalty_type, group.penalty_value),
            "gracePeriodDays": group.grace_period_days,
            "auctionCount": auction_stats.get(group.id, {}).get("auctionCount", 0),
            "openAuctionCount": auction_stats.get(group.id, {}).get("openAuctionCount", 0),
            "latestPaymentAt": latest_payment_at_by_group_id.get(group.id),
        }
        for group in groups
    ]


def list_owner_auctions(db: Session, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    rows = _owner_session_rows(db, owner.id)
    if not rows:
        return []

    group_by_id = _group_lookup(db, [session.group_id for session in rows])
    session_ids = [session.id for session in rows]
    highest_bid_by_session_id: dict[int, AuctionBid] = {}
    if session_ids:
        highest_bid_rows = db.scalars(
            select(AuctionBid)
            .where(
                AuctionBid.auction_session_id.in_(session_ids),
                AuctionBid.is_valid.is_(True),
            )
            .order_by(
                AuctionBid.auction_session_id.asc(),
                AuctionBid.bid_amount.desc(),
                AuctionBid.placed_at.asc(),
                AuctionBid.id.asc(),
            )
        ).all()
        for bid in highest_bid_rows:
            highest_bid_by_session_id.setdefault(bid.auction_session_id, bid)

    results = db.scalars(
        select(AuctionResult).where(AuctionResult.auction_session_id.in_(session_ids))
    ).all() if session_ids else []
    result_by_session_id = {
        result.auction_session_id: result
        for result in results
    }
    now = utcnow()
    membership_lookup = _membership_display_lookup(
        db,
        list(
            {
                bid.membership_id
                for bid in highest_bid_by_session_id.values()
            }
            | {
                result.winner_membership_id
                for result in results
            }
        ),
    )

    return [
        {
            "sessionId": session.id,
            "groupId": session.group_id,
            "groupCode": group_by_id.get(session.group_id).group_code if group_by_id.get(session.group_id) else "",
            "groupTitle": group_by_id.get(session.group_id).title if group_by_id.get(session.group_id) else "",
            "cycleNo": session.cycle_no,
            "auctionMode": session.auction_mode,
            "commissionMode": session.commission_mode,
            "commissionValue": money_int_or_none(session.commission_value),
            "minBidValue": session.min_bid_value,
            "maxBidValue": session.max_bid_value,
            "minIncrement": session.min_increment,
            "status": get_auction_state(
                session,
                now=now,
                has_result=session.id in result_by_session_id,
            ).lower(),
            "scheduledStartAt": session.scheduled_start_at,
            "actualStartAt": session.actual_start_at,
            "actualEndAt": session.actual_end_at,
            "highestBidAmount": (
                money_int(highest_bid_by_session_id[session.id].bid_amount)
                if session.id in highest_bid_by_session_id
                and ((session.auction_mode or "LIVE").upper() != "BLIND" or session.id in result_by_session_id)
                else None
            ),
            "highestBidMembershipNo": (
                membership_lookup.get(highest_bid_by_session_id[session.id].membership_id, {}).get("membershipNo")
                if session.id in highest_bid_by_session_id
                and ((session.auction_mode or "LIVE").upper() != "BLIND" or session.id in result_by_session_id)
                else None
            ),
            "highestBidderName": (
                membership_lookup.get(highest_bid_by_session_id[session.id].membership_id, {}).get("memberName")
                if session.id in highest_bid_by_session_id
                and ((session.auction_mode or "LIVE").upper() != "BLIND" or session.id in result_by_session_id)
                else None
            ),
            "winnerMembershipId": (
                result_by_session_id[session.id].winner_membership_id
                if session.id in result_by_session_id
                else None
            ),
            "winnerMembershipNo": (
                membership_lookup.get(result_by_session_id[session.id].winner_membership_id, {}).get("membershipNo")
                if session.id in result_by_session_id
                else None
            ),
            "winnerName": (
                membership_lookup.get(result_by_session_id[session.id].winner_membership_id, {}).get("memberName")
                if session.id in result_by_session_id
                else None
            ),
            "winningBidAmount": (
                money_int(result_by_session_id[session.id].winning_bid_amount)
                if session.id in result_by_session_id
                else None
            ),
            "finalizedAt": (
                result_by_session_id[session.id].finalized_at
                if session.id in result_by_session_id
                else None
            ),
            "createdAt": session.created_at,
        }
        for session in rows
    ]


def list_owner_payments(db: Session, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    payment_rows = _owner_payment_rows(db, owner.id)
    snapshot_map = build_membership_dues_snapshot_map(
        db,
        [membership_id for _payment, _group_id, _group_code, _group_title, membership_id in payment_rows if membership_id is not None],
    )

    subscriber_ids = [payment.subscriber_id for payment, *_rest in payment_rows]
    if not subscriber_ids:
        return []

    subscriber_names = {
        subscriber.id: subscriber.full_name
        for subscriber in db.scalars(select(Subscriber).where(Subscriber.id.in_(subscriber_ids))).all()
    }

    return [
        {
            "paymentId": payment.id,
            "groupId": group_id,
            "groupCode": group_code,
            "subscriberId": payment.subscriber_id,
            "subscriberName": subscriber_names.get(payment.subscriber_id, ""),
            "amount": money_int(payment.amount),
            "paymentDate": payment.payment_date,
            "paymentMethod": payment.payment_method,
            "status": payment.status,
            "createdAt": payment.created_at,
            **(
                snapshot_map[membership_id].as_dict()
                if membership_id is not None and membership_id in snapshot_map
                else {}
            ),
        }
        for payment, group_id, group_code, _group_title, membership_id in payment_rows
    ]


def list_owner_payouts(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    return list_payouts(
        db,
        current_user,
        subscriber_id=subscriber_id,
        group_id=group_id,
        page=page,
        page_size=page_size,
    )


def list_owner_activity(
    db: Session,
    current_user: CurrentUser,
    limit: int = 10,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)
    normalized_limit = _normalize_limit(limit, maximum=MAX_OWNER_ACTIVITY_LIMIT)
    fetch_limit = None if (page is not None or page_size is not None) else normalized_limit

    groups = _owner_recent_groups(db, owner.id, limit=fetch_limit)
    sessions = _owner_session_rows(db, owner.id, limit=fetch_limit)
    payments = _owner_payment_rows(db, owner.id, limit=fetch_limit)
    payouts = list_payouts(db, current_user)
    activity_group_ids = {
        group.id for group in groups
    } | {
        session.group_id for session in sessions
    } | {
        group_id for _payment, group_id, _group_code, _group_title, _membership_id in payments if group_id is not None
    } | {
        payout["groupId"] for payout in payouts if payout.get("groupId") is not None
    }
    group_codes_by_id = {
        group.id: group.group_code
        for group in _group_lookup(db, list(activity_group_ids)).values()
    }

    activity: list[dict] = []
    for group in groups:
        activity.append(
            {
                "kind": "group_created",
                "occurredAt": group.created_at,
                "groupId": group.id,
                "groupCode": group.group_code,
                "title": group.title,
                "detail": f"Group {group.group_code} was created",
                "refId": group.id,
            }
        )

    for session in sessions:
        activity.append(
            {
                "kind": "auction_session",
                "occurredAt": session.created_at,
                "groupId": session.group_id,
                "groupCode": group_codes_by_id.get(session.group_id),
                "title": f"Auction cycle {session.cycle_no}",
                "detail": f"Auction session {session.status}",
                "refId": session.id,
            }
        )

    for payment, group_id, group_code, _group_title, _membership_id in payments:
        activity.append(
            {
                "kind": "payment_recorded",
                "occurredAt": payment.created_at,
                "groupId": group_id,
                "groupCode": group_code,
                "title": "Payment recorded",
                "detail": f"Payment of {money_int(payment.amount)} recorded",
                "refId": payment.id,
            }
        )

    for payout in payouts:
        activity.append(
            {
                "kind": "payout_recorded",
                "occurredAt": payout["createdAt"],
                "groupId": payout["groupId"],
                "groupCode": payout["groupCode"],
                "title": "Payout recorded",
                "detail": f"Payout of {money_int(payout['netAmount'])} recorded",
                "refId": payout["id"],
            }
        )

    activity.sort(key=lambda item: item["occurredAt"], reverse=True)
    if page is None and page_size is None:
        return activity[:normalized_limit]

    resolved = resolve_pagination(page, page_size, default_page_size=normalized_limit)
    if resolved is None:
        return activity[:normalized_limit]
    start = (resolved.page - 1) * resolved.page_size
    end = start + resolved.page_size
    return build_paginated_response(activity[start:end], resolved, len(activity))


def list_owner_audit_logs(
    db: Session,
    current_user: CurrentUser,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_user_id: int | None = None,
    limit: int = 10,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)
    normalized_limit = _normalize_limit(limit, maximum=MAX_OWNER_AUDIT_LIMIT)
    statement = (
        select(AuditLog)
        .where(AuditLog.owner_id == owner.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    if action:
        statement = statement.where(AuditLog.action == action)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditLog.entity_id == str(entity_id))
    if actor_user_id is not None:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)

    pagination = resolve_pagination(page, page_size, default_page_size=normalized_limit)
    if pagination is None:
        audit_logs = db.scalars(statement.limit(normalized_limit)).all()
        actor_lookup = _build_actor_lookup(
            db,
            [audit_log.actor_user_id for audit_log in audit_logs if audit_log.actor_user_id is not None],
        )
        return [
            _serialize_owner_audit_log(audit_log, actor_lookup=actor_lookup)
            for audit_log in audit_logs
        ]

    total_count = count_statement(db, statement)
    audit_logs = db.scalars(apply_pagination(statement, pagination)).all()
    actor_lookup = _build_actor_lookup(
        db,
        [audit_log.actor_user_id for audit_log in audit_logs if audit_log.actor_user_id is not None],
    )
    return build_paginated_response(
        [
            _serialize_owner_audit_log(audit_log, actor_lookup=actor_lookup)
            for audit_log in audit_logs
        ],
        pagination,
        total_count,
    )


def get_owner_dashboard_report(db: Session, current_user: CurrentUser, activity_limit: int = 10) -> dict:
    owner = require_owner(current_user)
    normalized_limit = _normalize_limit(activity_limit, maximum=MAX_OWNER_ACTIVITY_LIMIT)
    groups = list_owner_groups(db, current_user)
    auctions = list_owner_auctions(db, current_user)
    payments = list_owner_payments(db, current_user)
    payouts = list_owner_payouts(db, current_user)
    balances = get_member_outstanding_totals(db, current_user)
    activity = list_owner_activity(db, current_user, limit=normalized_limit)
    audit_logs = list_owner_audit_logs(db, current_user, limit=normalized_limit)

    total_due_amount = sum(group["totalDue"] for group in groups)
    total_paid_amount = sum(group["totalPaid"] for group in groups)
    total_outstanding_amount = sum(group["outstandingAmount"] for group in groups)
    total_payout_amount = sum(payout["netAmount"] for payout in payouts)

    return {
        "ownerId": owner.id,
        "groupCount": len(groups),
        "auctionCount": len(auctions),
        "paymentCount": len(payments),
        "payoutCount": len(payouts),
        "totalDueAmount": money_int(total_due_amount),
        "totalPaidAmount": money_int(total_paid_amount),
        "totalOutstandingAmount": money_int(total_outstanding_amount),
        "totalPayoutAmount": money_int(total_payout_amount),
        "groups": groups,
        "recentAuctions": auctions[:normalized_limit],
        "recentPayments": payments[:normalized_limit],
        "recentPayouts": payouts[:normalized_limit],
        "balances": balances,
        "recentActivity": activity,
        "recentAuditLogs": audit_logs,
    }
