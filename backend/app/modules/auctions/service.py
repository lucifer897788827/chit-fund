import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Thread
from time import perf_counter
from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.logging import APP_LOGGER_NAME
from app.core.money import money_int
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.core.time import utcnow
from app.models.auction import AuctionBid, AuctionResult, AuctionSession, FinalizeJob
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import LedgerEntry, Payment, Payout
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.commission_service import calculate_owner_commission_amount
from app.modules.groups.slot_service import (
    build_membership_slot_summary,
    get_membership_bid_eligibility,
    mark_membership_slot_won,
    release_membership_won_slot,
)
from app.modules.auctions.realtime_service import (
    publish_auction_bid_event,
    publish_auction_finalize_event,
)
from app.modules.notifications.service import (
    dispatch_staged_notifications,
    notify_auction_finalized,
)
from app.modules.payments.auction_payout_engine import AuctionPayoutCalculation, calculate_payout
from app.modules.payments.installment_service import rebuild_installment_from_payments
from app.modules.payments.ledger_service import ensure_payment_ledger_entry
from app.modules.payments.payout_service import ensure_auction_payout


DEFAULT_MIN_BID_VALUE = 0
DEFAULT_MIN_INCREMENT = 1
logger = logging.getLogger(APP_LOGGER_NAME)
FINALIZE_JOB_ERROR_LIMIT = 1800


def _log_finalize_trace(
    message: str,
    *,
    session_id: int,
    group_id: int | None = None,
    step: str | None = None,
    duration_ms: float | None = None,
    **extra_fields,
) -> None:
    extra_payload: dict[str, object] = {
        "event": "auction.finalize.trace",
        "session_id": int(session_id),
    }
    if group_id is not None:
        extra_payload["group_id"] = int(group_id)
    if step is not None:
        extra_payload["step"] = step
    if duration_ms is not None:
        extra_payload["duration_ms"] = round(duration_ms, 2)
    extra_payload.update(extra_fields)
    logger.info(message, extra=extra_payload)


@dataclass(slots=True)
class AuctionSessionSnapshot:
    id: int
    group_id: int
    cycle_no: int
    scheduled_start_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    start_time: datetime | None
    end_time: datetime | None
    auction_mode: str | None
    commission_mode: str | None
    commission_value: int | None
    min_bid_value: int | None
    max_bid_value: int | None
    min_increment: int | None
    bidding_window_seconds: int
    status: str
    opened_by_user_id: int | None
    closed_by_user_id: int | None
    winning_bid_id: int | None
    updated_at: datetime


@dataclass(slots=True)
class ChitGroupSnapshot:
    id: int
    owner_id: int
    group_code: str
    title: str
    chit_value: int
    installment_amount: int
    member_count: int
    cycle_count: int


@dataclass(slots=True)
class AuctionResultSnapshot:
    id: int
    auction_session_id: int
    group_id: int
    cycle_no: int
    winner_membership_id: int
    winning_bid_id: int
    winning_bid_amount: int
    dividend_pool_amount: int
    dividend_per_member_amount: int
    owner_commission_amount: int
    winner_payout_amount: int
    finalized_by_user_id: int
    finalized_at: datetime


@dataclass(slots=True)
class WinningBidSnapshot:
    id: int
    membership_id: int
    bid_amount: int


@dataclass(slots=True)
class FinalizeReadContext:
    session: AuctionSessionSnapshot
    group: ChitGroupSnapshot
    result: AuctionResultSnapshot | None
    total_bid_count: int
    valid_bid_count: int
    has_payout: bool
    result_winner_details: dict[str, int | str | None] | None


@dataclass(slots=True)
class FinalizeEnqueueContext:
    session: AuctionSessionSnapshot
    group: ChitGroupSnapshot
    has_valid_bid: bool


def get_auction_mode(session: AuctionSession) -> str:
    return (session.auction_mode or "LIVE").upper()


def is_fixed_auction(session: AuctionSession) -> bool:
    return get_auction_mode(session) == "FIXED"


def is_blind_auction(session: AuctionSession) -> bool:
    return get_auction_mode(session) == "BLIND"


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _normalize_datetime_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value)


def _normalize_bid_control_value(value: int | float | None, *, fallback: int) -> int:
    if value is None:
        return int(fallback)
    return int(value)


def resolve_session_bid_controls(
    *,
    session: AuctionSession | None = None,
    group: ChitGroup,
    min_bid_value: int | float | None = None,
    max_bid_value: int | float | None = None,
    min_increment: int | float | None = None,
) -> dict[str, int]:
    resolved_min_bid_value = _normalize_bid_control_value(
        session.min_bid_value if session is not None else min_bid_value,
        fallback=DEFAULT_MIN_BID_VALUE,
    )
    resolved_max_bid_value = _normalize_bid_control_value(
        session.max_bid_value if session is not None else max_bid_value,
        fallback=money_int(group.chit_value),
    )
    resolved_min_increment = _normalize_bid_control_value(
        session.min_increment if session is not None else min_increment,
        fallback=DEFAULT_MIN_INCREMENT,
    )
    return {
        "minBidValue": resolved_min_bid_value,
        "maxBidValue": resolved_max_bid_value,
        "minIncrement": resolved_min_increment,
    }


def validate_session_bid_controls(
    *,
    group: ChitGroup,
    min_bid_value: int | float | None,
    max_bid_value: int | float | None,
    min_increment: int | float | None,
) -> dict[str, int]:
    controls = resolve_session_bid_controls(
        group=group,
        min_bid_value=min_bid_value,
        max_bid_value=max_bid_value,
        min_increment=min_increment,
    )
    if controls["minBidValue"] < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Minimum bid value cannot be negative",
        )
    if controls["maxBidValue"] < controls["minBidValue"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum bid value must be greater than or equal to minimum bid value",
        )
    if controls["minIncrement"] < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Minimum increment must be at least 1",
        )
    return controls


def get_session_bid_controls(db: Session, session: AuctionSession) -> dict[str, int]:
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")
    return resolve_session_bid_controls(session=session, group=group)


def validate_bid_amount_for_session(db: Session, session: AuctionSession, *, bid_amount: int) -> dict[str, int]:
    controls = get_session_bid_controls(db, session)
    if bid_amount < controls["minBidValue"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid amount is below minimum allowed value",
        )
    if bid_amount > controls["maxBidValue"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid amount is above maximum allowed value",
        )
    if (int(bid_amount) - controls["minBidValue"]) % controls["minIncrement"] != 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid amount does not satisfy minimum increment",
        )
    return controls


def get_auction_session_start_at(session: AuctionSession) -> datetime:
    return _normalize_datetime(session.actual_start_at or session.scheduled_start_at)


def get_auction_session_window_start(session: AuctionSession) -> datetime:
    if is_blind_auction(session):
        configured_start = _normalize_datetime_or_none(session.start_time)
        if configured_start is not None:
            return configured_start
    return get_auction_session_start_at(session)


def get_auction_session_deadline(session: AuctionSession) -> datetime:
    if is_blind_auction(session):
        configured_end = _normalize_datetime_or_none(session.end_time)
        if configured_end is not None:
            return configured_end
    return get_auction_session_start_at(session) + timedelta(seconds=session.bidding_window_seconds)


def is_auction_bidding_open(session: AuctionSession, *, now: datetime | None = None) -> bool:
    if session.status != "open":
        return False
    current_time = _normalize_datetime(now or utcnow())
    return get_auction_session_window_start(session) <= current_time < get_auction_session_deadline(session)


def get_auction_state(
    session: AuctionSession,
    *,
    now: datetime | None = None,
    has_result: bool = False,
) -> str:
    if has_result or session.status == "finalized":
        return "FINALIZED"

    current_time = _normalize_datetime(now or utcnow())
    starts_at = get_auction_session_window_start(session)
    ends_at = get_auction_session_deadline(session)
    normalized_status = (session.status or "").lower()

    if normalized_status in {"closed", "settled"}:
        return "ENDED"
    if normalized_status != "open":
        return normalized_status.upper() if normalized_status else "UNKNOWN"
    if current_time < starts_at:
        return "UPCOMING"
    if current_time >= ends_at:
        return "ENDED"
    return "OPEN"


def list_expired_open_auction_sessions(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[AuctionSession]:
    cutoff = _normalize_datetime(now or utcnow())
    query = select(AuctionSession).where(AuctionSession.status == "open").order_by(AuctionSession.id.asc())
    open_sessions = db.scalars(query).all()
    expired_sessions = [session for session in open_sessions if get_auction_session_deadline(session) <= cutoff]
    if limit is not None:
        return expired_sessions[:limit]
    return expired_sessions


def can_finalize_auction_session(db: Session, session: AuctionSession, *, now: datetime | None = None) -> bool:
    if session.status not in {"open", "closed"}:
        return False
    current_time = _normalize_datetime(now or utcnow())
    if is_blind_auction(session) and session.status == "open" and current_time < get_auction_session_deadline(session):
        return False
    if is_fixed_auction(session):
        return _get_fixed_mode_winner_membership(db, session) is not None
    valid_bid_count = _get_valid_bid_count(db, session.id)
    if valid_bid_count > 0:
        return True
    if session.status == "closed":
        return True
    return current_time >= get_auction_session_deadline(session)


def _get_membership_for_current_user(
    db: Session,
    session: AuctionSession,
    current_user: CurrentUser,
    *,
    for_update: bool = False,
) -> GroupMembership:
    subscriber = require_subscriber(current_user)
    query = select(GroupMembership).where(
        GroupMembership.group_id == session.group_id,
        GroupMembership.subscriber_id == subscriber.id,
    )
    if for_update:
        query = query.with_for_update()
    membership = db.scalar(query)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this auction")
    return membership


def _get_membership_bid_capacity(
    db: Session,
    session: AuctionSession,
    membership: GroupMembership,
    bidder_user_id: int,
    *,
    slot_summary=None,
) -> dict[str, int]:
    resolved_slot_summary = slot_summary or build_membership_slot_summary(db, membership)
    bid_count = db.scalar(
        select(func.count(AuctionBid.id)).where(
            AuctionBid.auction_session_id == session.id,
            AuctionBid.bidder_user_id == bidder_user_id,
            AuctionBid.is_valid.is_(True),
        )
    ) or 0
    bid_count = int(bid_count)
    bid_limit = int(resolved_slot_summary.available_slots)
    remaining_bid_capacity = max(bid_limit - bid_count, 0)
    return {
        "bidCount": bid_count,
        "bidLimit": bid_limit,
        "remainingBidCapacity": remaining_bid_capacity,
    }


def _build_membership_slot_payload(slot_summary) -> dict[str, int]:
    return {
        "mySlotCount": int(slot_summary.total_slots),
        "myWonSlotCount": int(slot_summary.won_slots),
        "myRemainingSlotCount": int(slot_summary.available_slots),
        "slotCount": int(slot_summary.total_slots),
        "wonSlotCount": int(slot_summary.won_slots),
        "remainingSlotCount": int(slot_summary.available_slots),
    }


def _get_valid_bid_count(db: Session, session_id: int) -> int:
    valid_bid_count = db.scalar(
        select(func.count(AuctionBid.id)).where(
            AuctionBid.auction_session_id == session_id,
            AuctionBid.is_valid.is_(True),
        )
    ) or 0
    return int(valid_bid_count)


def _get_bid_count_snapshot(db: Session, session_id: int) -> tuple[int, int]:
    total_bids, valid_bid_count = db.execute(
        select(
            func.count(AuctionBid.id),
            func.coalesce(
                func.sum(
                    case(
                        (AuctionBid.is_valid.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(AuctionBid.auction_session_id == session_id)
    ).one()
    return int(total_bids or 0), int(valid_bid_count or 0)


def _get_no_bid_finalization_message(
    *,
    session: AuctionSession,
    result: AuctionResult | None,
    valid_bid_count: int,
) -> str | None:
    if session.status == "finalizing" and result is None:
        return "Auction finalization queued."
    if result is not None:
        return "Auction closed and finalized."
    if session.status == "finalized" and valid_bid_count == 0:
        return "Auction finalized with no winner because no bids were received."
    return None


def _get_membership_display_details(db: Session, membership_id: int | None) -> dict[str, int | str | None]:
    if membership_id is None:
        return {
            "winnerMembershipId": None,
            "winnerMembershipNo": None,
            "winnerName": None,
        }

    membership = db.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    if membership is None:
        return {
            "winnerMembershipId": membership_id,
            "winnerMembershipNo": None,
            "winnerName": None,
        }

    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == membership.subscriber_id))
    return {
        "winnerMembershipId": membership.id,
        "winnerMembershipNo": membership.member_no,
        "winnerName": subscriber.full_name if subscriber is not None else None,
    }


def _get_membership_display_details_joined(db: Session, membership_id: int | None) -> dict[str, int | str | None]:
    if membership_id is None:
        return {
            "winnerMembershipId": None,
            "winnerMembershipNo": None,
            "winnerName": None,
        }

    row = db.execute(
        select(GroupMembership.id, GroupMembership.member_no, Subscriber.full_name)
        .outerjoin(Subscriber, Subscriber.id == GroupMembership.subscriber_id)
        .where(GroupMembership.id == membership_id)
    ).one_or_none()
    if row is None:
        return {
            "winnerMembershipId": membership_id,
            "winnerMembershipNo": None,
            "winnerName": None,
        }

    winner_membership_id, winner_membership_no, winner_name = row
    return {
        "winnerMembershipId": winner_membership_id,
        "winnerMembershipNo": winner_membership_no,
        "winnerName": winner_name,
    }


def _get_user_display_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None

    owner = db.scalar(select(Owner).where(Owner.user_id == user_id))
    if owner is not None:
        return owner.display_name

    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user_id))
    if subscriber is not None:
        return subscriber.full_name

    return f"User #{user_id}"


def _get_fixed_mode_winner_membership(db: Session, session: AuctionSession) -> GroupMembership | None:
    memberships = db.scalars(
        select(GroupMembership)
        .where(GroupMembership.group_id == session.group_id)
        .order_by(GroupMembership.member_no.asc(), GroupMembership.id.asc())
    ).all()
    for membership in memberships:
        if get_membership_bid_eligibility(db, membership):
            return membership
    return None


def _get_or_create_fixed_mode_bid(
    db: Session,
    *,
    session: AuctionSession,
    membership: GroupMembership,
    placed_at: datetime,
) -> AuctionBid:
    idempotency_key = f"fixed-auto-{session.id}-{membership.id}"
    existing_bid = db.scalar(
        select(AuctionBid).where(
            AuctionBid.auction_session_id == session.id,
            AuctionBid.membership_id == membership.id,
            AuctionBid.idempotency_key == idempotency_key,
        )
    )
    if existing_bid is not None:
        return existing_bid

    subscriber = db.get(Subscriber, membership.subscriber_id)
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found for fixed auction")

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key=idempotency_key,
        bid_amount=0,
        bid_discount_amount=0,
        placed_at=placed_at,
        is_valid=True,
    )
    db.add(bid)
    db.flush()
    return bid


def _session_has_valid_bid(db: Session, session_id: int) -> bool:
    return db.scalar(
        select(AuctionBid.id)
        .where(
            AuctionBid.auction_session_id == session_id,
            AuctionBid.is_valid.is_(True),
        )
        .limit(1)
    ) is not None


def _can_enqueue_finalize_request(
    db: Session,
    *,
    session: AuctionSession,
    current_time: datetime,
) -> bool:
    if session.status in {"finalizing", "finalized", "closed"}:
        return True
    if session.status != "open":
        return False
    if is_blind_auction(session) and current_time < get_auction_session_deadline(session):
        return False
    if is_fixed_auction(session):
        return True
    if _session_has_valid_bid(db, session.id):
        return True
    return current_time >= get_auction_session_deadline(session)


def _serialize_auction_audit_state(session: AuctionSession, result: AuctionResult | None = None) -> dict:
    return {
        "status": session.status,
        "actualEndAt": session.actual_end_at,
        "closedByUserId": session.closed_by_user_id,
        "winningBidId": result.winning_bid_id if result is not None else session.winning_bid_id,
        "winnerMembershipId": result.winner_membership_id if result is not None else None,
        "winningBidAmount": (
                money_int(result.winning_bid_amount)
            if result is not None and result.winning_bid_amount is not None
            else None
        ),
        "finalizedAt": (
            result.finalized_at
            if result is not None
            else session.updated_at if session.status == "finalized" else None
        ),
    }


def get_room(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")

    membership = _get_membership_for_current_user(db, session, current_user)
    slot_summary = build_membership_slot_summary(db, membership)
    bid_capacity = _get_membership_bid_capacity(
        db,
        session,
        membership,
        current_user.user.id,
        slot_summary=slot_summary,
    )
    bid_controls = get_session_bid_controls(db, session)

    last_bid = db.scalar(
        select(AuctionBid)
        .where(
            AuctionBid.auction_session_id == session.id,
            AuctionBid.bidder_user_id == current_user.user.id,
        )
        .order_by(AuctionBid.id.desc())
    )

    result = db.scalar(
        select(AuctionResult).where(AuctionResult.auction_session_id == session.id)
    )
    valid_bid_count = _get_valid_bid_count(db, session.id)
    can_bid = session.status == "open" and slot_summary.can_bid
    room_result = None
    if result is not None:
        room_result = {
            "winningBidId": result.winning_bid_id,
            "winnerMembershipId": result.winner_membership_id,
            "winningBidAmount": money_int(result.winning_bid_amount),
            "finalizedAt": result.finalized_at,
        }
    now = utcnow()
    starts_at = get_auction_session_window_start(session)
    ends_at = get_auction_session_deadline(session)

    return {
        "sessionId": session.id,
        "groupId": session.group_id,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "minBidValue": bid_controls["minBidValue"],
        "maxBidValue": bid_controls["maxBidValue"],
        "minIncrement": bid_controls["minIncrement"],
        "auctionState": get_auction_state(session, now=now, has_result=result is not None),
        "status": session.status,
        "cycleNo": session.cycle_no,
        "serverTime": now,
        "startsAt": starts_at,
        "endsAt": ends_at,
        "canBid": (
            can_bid
            and not is_fixed_auction(session)
            and is_auction_bidding_open(session, now=now)
            and bid_capacity["remainingBidCapacity"] > 0
        ),
        "myMembershipId": membership.id,
        "myLastBid": money_int(last_bid.bid_amount) if last_bid else None,
        "myBidCount": bid_capacity["bidCount"],
        "myBidLimit": bid_capacity["bidLimit"],
        "myRemainingBidCapacity": bid_capacity["remainingBidCapacity"],
        **_build_membership_slot_payload(slot_summary),
        "validBidCount": valid_bid_count,
        "finalizationMessage": _get_no_bid_finalization_message(
            session=session,
            result=result,
            valid_bid_count=valid_bid_count,
        ),
        "result": room_result,
    }


def place_bid(db: Session, session_id: int, payload, current_user: CurrentUser) -> dict:
    session = db.scalar(
        select(AuctionSession).where(AuctionSession.id == session_id).with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    if session.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session is not open")
    if is_fixed_auction(session):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fixed auctions do not accept bids")

    membership = _get_membership_for_current_user(db, session, current_user, for_update=True)
    if not get_membership_bid_eligibility(db, membership):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership is not eligible to bid")

    existing_bid = db.scalar(
        select(AuctionBid).where(
            AuctionBid.auction_session_id == session.id,
            AuctionBid.bidder_user_id == current_user.user.id,
            AuctionBid.idempotency_key == payload.idempotencyKey,
        )
    )
    if existing_bid is not None:
        room_snapshot = get_room(db, session.id, current_user)
        return {
            "accepted": True,
            "bidId": existing_bid.id,
            "placedAt": existing_bid.placed_at,
            "sessionStatus": session.status,
            "room": room_snapshot,
        }

    now = utcnow()
    if not is_auction_bidding_open(session, now=now):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auction bidding window is closed",
        )
    validate_bid_amount_for_session(db, session, bid_amount=int(payload.bidAmount))
    bid_capacity = _get_membership_bid_capacity(db, session, membership, current_user.user.id)
    if bid_capacity["remainingBidCapacity"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid limit reached for this session",
        )
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=current_user.user.id,
        idempotency_key=payload.idempotencyKey,
        bid_amount=payload.bidAmount,
        bid_discount_amount=0,
        placed_at=now,
        is_valid=True,
    )
    db.add(bid)
    db.flush()
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    log_audit_event(
        db,
        action="auction.bid.placed",
        entity_type="auction_bid",
        entity_id=bid.id,
        current_user=current_user,
        owner_id=group.owner_id if group is not None else None,
        metadata={
            "auctionSessionId": session.id,
            "bidAmount": money_int(bid.bid_amount),
            "membershipId": membership.id,
        },
        before={
            "bidCount": bid_capacity["bidCount"],
            "remainingBidCapacity": bid_capacity["remainingBidCapacity"],
            "sessionStatus": session.status,
        },
        after={
            "auctionSessionId": session.id,
            "membershipId": membership.id,
            "bidId": bid.id,
            "bidAmount": money_int(bid.bid_amount),
            "placedAt": bid.placed_at,
            "bidCount": bid_capacity["bidCount"] + 1,
            "remainingBidCapacity": max(bid_capacity["remainingBidCapacity"] - 1, 0),
            "sessionStatus": session.status,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_bid = db.scalar(
            select(AuctionBid).where(
                AuctionBid.auction_session_id == session.id,
                AuctionBid.bidder_user_id == current_user.user.id,
                AuctionBid.idempotency_key == payload.idempotencyKey,
            )
        )
        if existing_bid is None:
            raise
        room_snapshot = get_room(db, session.id, current_user)
        return {
            "accepted": True,
            "bidId": existing_bid.id,
            "placedAt": existing_bid.placed_at,
            "sessionStatus": session.status,
            "room": room_snapshot,
        }
    db.refresh(bid)
    room_snapshot = get_room(db, session.id, current_user)
    try:
        publish_auction_bid_event(
            session.id,
            {
                "room": room_snapshot,
                "bidId": bid.id,
            },
        )
    except Exception:
        logger.exception(
            "Auction bid event publish failed after commit",
            extra={
                "event": "auction.bid.publish_failed",
                "auction_session_id": session.id,
                "bid_id": bid.id,
            },
        )

    return {
        "accepted": True,
        "bidId": bid.id,
        "placedAt": bid.placed_at,
        "sessionStatus": session.status,
        "room": room_snapshot,
    }


def persist_auction_result(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup | None = None,
    winning_bid: AuctionBid,
    winner_membership_id: int,
    winner_membership: GroupMembership | None = None,
    finalized_by_user_id: int,
    finalized_at: datetime | None = None,
    dividend_pool_amount: int,
    dividend_per_member_amount: int,
    owner_commission_amount: int,
    winner_payout_amount: int,
    payout_calculation: AuctionPayoutCalculation | None = None,
) -> AuctionResult:
    if winning_bid.auction_session_id != session.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Winning bid does not belong to this session")

    winner_membership = winner_membership or db.scalar(
        select(GroupMembership).where(
            GroupMembership.id == winner_membership_id,
            GroupMembership.group_id == session.group_id,
        )
    )
    if winner_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Winner membership not found")
    if winning_bid.membership_id != winner_membership.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Winning bid does not belong to winner")

    existing_result = db.scalar(
        select(AuctionResult).where(AuctionResult.auction_session_id == session.id)
    )
    should_advance_group = existing_result is None and session.status != "finalized"
    previous_winner_membership: GroupMembership | None = None
    if existing_result is not None and existing_result.winner_membership_id != winner_membership.id:
        previous_winner_membership = db.scalar(
            select(GroupMembership).where(GroupMembership.id == existing_result.winner_membership_id)
        )
        if previous_winner_membership is not None:
            release_membership_won_slot(db, previous_winner_membership)
            previous_winner_membership.updated_at = utcnow()

    closed_at = finalized_at or utcnow()
    session.status = "closed"
    session.winning_bid_id = winning_bid.id
    session.actual_end_at = closed_at
    session.closed_by_user_id = finalized_by_user_id
    session.updated_at = utcnow()

    if existing_result is None or existing_result.winner_membership_id != winner_membership.id:
        mark_membership_slot_won(db, winner_membership, cycle_no=session.cycle_no)
    else:
        winner_membership.prized_cycle_no = session.cycle_no
    winner_membership.updated_at = utcnow()

    resolved_group = group or db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if resolved_group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")
    if should_advance_group:
        _advance_group_cycle(resolved_group, session)

    if existing_result is None:
        result = AuctionResult(
            auction_session_id=session.id,
            group_id=session.group_id,
            cycle_no=session.cycle_no,
            winner_membership_id=winner_membership.id,
            winning_bid_id=winning_bid.id,
            winning_bid_amount=winning_bid.bid_amount,
            dividend_pool_amount=dividend_pool_amount,
            dividend_per_member_amount=dividend_per_member_amount,
            owner_commission_amount=owner_commission_amount,
            winner_payout_amount=winner_payout_amount,
            finalized_by_user_id=finalized_by_user_id,
            finalized_at=closed_at,
        )
        db.add(result)
    else:
        result = existing_result
        result.group_id = session.group_id
        result.cycle_no = session.cycle_no
        result.winner_membership_id = winner_membership.id
        result.winning_bid_id = winning_bid.id
        result.winning_bid_amount = winning_bid.bid_amount
        result.dividend_pool_amount = dividend_pool_amount
        result.dividend_per_member_amount = dividend_per_member_amount
        result.owner_commission_amount = owner_commission_amount
        result.winner_payout_amount = winner_payout_amount
        result.finalized_by_user_id = finalized_by_user_id
        result.finalized_at = closed_at

    db.flush()
    ensure_auction_payout(
        db,
        result=result,
        group=resolved_group,
        membership=winner_membership,
        membership_payables=(
            payout_calculation.membership_payables
            if payout_calculation is not None
            else None
        ),
    )
    return result


def select_winning_bid(db: Session, session_id: int) -> AuctionBid | None:
    return db.scalar(
        select(AuctionBid)
        .where(
            AuctionBid.auction_session_id == session_id,
            AuctionBid.is_valid.is_(True),
        )
        .order_by(
            AuctionBid.bid_amount.desc(),
            AuctionBid.placed_at.asc(),
            AuctionBid.id.asc(),
        )
    )


def _load_finalize_read_context(
    db: Session,
    *,
    session_id: int,
    current_user: CurrentUser,
) -> FinalizeReadContext:
    owner = require_owner(current_user)
    row = db.execute(
        text(
            """
            SELECT
                s.id AS session_id,
                s.group_id AS session_group_id,
                s.cycle_no,
                s.scheduled_start_at,
                s.actual_start_at,
                s.actual_end_at,
                s.start_time,
                s.end_time,
                s.auction_mode,
                s.commission_mode,
                s.commission_value,
                s.min_bid_value,
                s.max_bid_value,
                s.min_increment,
                s.bidding_window_seconds,
                s.status AS session_status,
                s.opened_by_user_id,
                s.closed_by_user_id,
                s.winning_bid_id AS session_winning_bid_id,
                s.updated_at AS session_updated_at,
                g.id AS group_id,
                g.owner_id AS group_owner_id,
                g.group_code,
                g.title,
                g.chit_value,
                g.installment_amount,
                g.member_count,
                g.cycle_count,
                r.id AS result_id,
                r.auction_session_id AS result_auction_session_id,
                r.group_id AS result_group_id,
                r.cycle_no AS result_cycle_no,
                r.winner_membership_id,
                r.winning_bid_id AS result_winning_bid_id,
                r.winning_bid_amount,
                r.dividend_pool_amount,
                r.dividend_per_member_amount,
                r.owner_commission_amount,
                r.winner_payout_amount,
                r.finalized_by_user_id,
                r.finalized_at,
                r_gm.member_no AS result_winner_membership_no,
                r_sub.full_name AS result_winner_name,
                COALESCE(b.total_bid_count, 0) AS total_bid_count,
                COALESCE(b.valid_bid_count, 0) AS valid_bid_count,
                CASE WHEN p.id IS NULL THEN 0 ELSE 1 END AS has_payout
            FROM auction_sessions AS s
            JOIN chit_groups AS g
                ON g.id = s.group_id
            LEFT JOIN auction_results AS r
                ON r.auction_session_id = s.id
            LEFT JOIN group_memberships AS r_gm
                ON r_gm.id = r.winner_membership_id
            LEFT JOIN subscribers AS r_sub
                ON r_sub.id = r_gm.subscriber_id
            LEFT JOIN (
                SELECT
                    auction_session_id,
                    COUNT(*) AS total_bid_count,
                    SUM(CASE WHEN is_valid IS TRUE THEN 1 ELSE 0 END) AS valid_bid_count
                FROM auction_bids
                WHERE auction_session_id = :session_id
                GROUP BY auction_session_id
            ) AS b
                ON b.auction_session_id = s.id
            LEFT JOIN payouts AS p
                ON p.auction_result_id = r.id
            WHERE s.id = :session_id
            LIMIT 1
            """
        ),
        {"session_id": int(session_id)},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    if int(row["group_owner_id"]) != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot finalize another owner's auction")

    session_snapshot = AuctionSessionSnapshot(
        id=int(row["session_id"]),
        group_id=int(row["session_group_id"]),
        cycle_no=int(row["cycle_no"]),
        scheduled_start_at=_coerce_datetime(row["scheduled_start_at"]),
        actual_start_at=_coerce_datetime(row["actual_start_at"]),
        actual_end_at=_coerce_datetime(row["actual_end_at"]),
        start_time=_coerce_datetime(row["start_time"]),
        end_time=_coerce_datetime(row["end_time"]),
        auction_mode=row["auction_mode"],
        commission_mode=row["commission_mode"],
        commission_value=row["commission_value"],
        min_bid_value=row["min_bid_value"],
        max_bid_value=row["max_bid_value"],
        min_increment=row["min_increment"],
        bidding_window_seconds=int(row["bidding_window_seconds"]),
        status=row["session_status"],
        opened_by_user_id=row["opened_by_user_id"],
        closed_by_user_id=row["closed_by_user_id"],
        winning_bid_id=row["session_winning_bid_id"],
        updated_at=_coerce_datetime(row["session_updated_at"]),
    )
    group_snapshot = ChitGroupSnapshot(
        id=int(row["group_id"]),
        owner_id=int(row["group_owner_id"]),
        group_code=row["group_code"],
        title=row["title"],
        chit_value=int(row["chit_value"]),
        installment_amount=int(row["installment_amount"]),
        member_count=int(row["member_count"]),
        cycle_count=int(row["cycle_count"]),
    )
    result_snapshot = None
    if row["result_id"] is not None:
        result_snapshot = AuctionResultSnapshot(
            id=int(row["result_id"]),
            auction_session_id=int(row["result_auction_session_id"]),
            group_id=int(row["result_group_id"]),
            cycle_no=int(row["result_cycle_no"]),
            winner_membership_id=int(row["winner_membership_id"]),
            winning_bid_id=int(row["result_winning_bid_id"]),
            winning_bid_amount=int(row["winning_bid_amount"]),
            dividend_pool_amount=int(row["dividend_pool_amount"]),
            dividend_per_member_amount=int(row["dividend_per_member_amount"]),
            owner_commission_amount=int(row["owner_commission_amount"]),
            winner_payout_amount=int(row["winner_payout_amount"]),
            finalized_by_user_id=int(row["finalized_by_user_id"]),
            finalized_at=_coerce_datetime(row["finalized_at"]),
        )

    return FinalizeReadContext(
        session=session_snapshot,
        group=group_snapshot,
        result=result_snapshot,
        total_bid_count=int(row["total_bid_count"] or 0),
        valid_bid_count=int(row["valid_bid_count"] or 0),
        has_payout=bool(row["has_payout"]),
        result_winner_details=(
            {
                "winnerMembershipId": int(row["winner_membership_id"]),
                "winnerMembershipNo": row["result_winner_membership_no"],
                "winnerName": row["result_winner_name"],
            }
            if row["winner_membership_id"] is not None
            else None
        ),
    )


def _select_live_winning_bid_snapshot(
    db: Session,
    *,
    session_id: int,
) -> tuple[WinningBidSnapshot | None, dict[str, int | str | None] | None]:
    row = db.execute(
        text(
            """
            SELECT
                b.id,
                b.membership_id,
                b.bid_amount,
                gm.member_no AS winner_membership_no,
                sub.full_name AS winner_name
            FROM auction_bids AS b
            JOIN group_memberships AS gm
                ON gm.id = b.membership_id
            LEFT JOIN subscribers AS sub
                ON sub.id = gm.subscriber_id
            WHERE b.auction_session_id = :session_id
              AND b.is_valid IS TRUE
            ORDER BY b.bid_amount DESC, b.placed_at ASC, b.id ASC
            LIMIT 1
            """
        ),
        {"session_id": int(session_id)},
    ).mappings().first()

    if row is None:
        return None, None
    return (
        WinningBidSnapshot(
            id=int(row["id"]),
            membership_id=int(row["membership_id"]),
            bid_amount=int(row["bid_amount"]),
        ),
        {
            "winnerMembershipId": int(row["membership_id"]),
            "winnerMembershipNo": row["winner_membership_no"],
            "winnerName": row["winner_name"],
        },
    )


def _can_finalize_from_snapshot(
    *,
    session: AuctionSessionSnapshot,
    valid_bid_count: int,
    current_time: datetime,
) -> bool:
    if session.status not in {"open", "closed"}:
        return False
    if is_blind_auction(session) and session.status == "open" and current_time < get_auction_session_deadline(session):
        return False
    if valid_bid_count > 0:
        return True
    if session.status == "closed":
        return True
    return current_time >= get_auction_session_deadline(session)


def create_auction_result(
    db: Session,
    *,
    session_id: int,
    finalized_by_user_id: int,
    session: AuctionSession | None = None,
    group: ChitGroup | None = None,
) -> AuctionResult | None:
    session = session or db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")

    group = group or db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")

    winner_membership: GroupMembership | None = None
    if is_fixed_auction(session):
        winner_membership = _get_fixed_mode_winner_membership(db, session)
        if winner_membership is None:
            return None
        winning_bid = _get_or_create_fixed_mode_bid(
            db,
            session=session,
            membership=winner_membership,
            placed_at=utcnow(),
        )
        winner_membership_id = winner_membership.id
    else:
        winning_bid = select_winning_bid(db, session_id)
        if winning_bid is None:
            return None
        winner_membership_id = winning_bid.membership_id

    payout_calculation = calculate_payout(
        db,
        session=session,
        group=group,
        winning_bid=winning_bid,
        winner_membership_id=winner_membership_id,
    )

    return persist_auction_result(
        db,
        session=session,
        group=group,
        winning_bid=winning_bid,
        winner_membership_id=winner_membership_id,
        winner_membership=winner_membership,
        finalized_by_user_id=finalized_by_user_id,
        finalized_at=utcnow(),
        dividend_pool_amount=money_int(payout_calculation.dividend_pool_amount),
        dividend_per_member_amount=money_int(payout_calculation.dividend_per_member_amount),
        owner_commission_amount=money_int(payout_calculation.owner_commission_amount),
        winner_payout_amount=money_int(payout_calculation.winner_payout_amount),
        payout_calculation=payout_calculation,
    )


def _build_minimal_payout_snapshot(
    *,
    session: AuctionSession,
    group: ChitGroup,
    winning_bid_amount: int,
) -> dict[str, int]:
    chit_value = money_int(group.chit_value)
    installment_amount = money_int(group.installment_amount)

    if is_fixed_auction(session):
        winner_payout_amount = chit_value - installment_amount
        return {
            "ownerCommissionAmount": 0,
            "dividendPoolAmount": 0,
            "dividendPerMemberAmount": 0,
            "winnerPayoutAmount": winner_payout_amount,
        }

    total_slots = max(int(group.member_count or 0), 1)
    owner_commission_amount = calculate_owner_commission_amount(
        session=session,
        group=group,
        winning_bid_amount=int(winning_bid_amount),
    )
    dividend_pool_amount = max(int(winning_bid_amount) - owner_commission_amount, 0)
    dividend_per_member_amount = dividend_pool_amount // total_slots
    winner_payout_amount = chit_value - int(winning_bid_amount) - installment_amount + dividend_per_member_amount
    return {
        "ownerCommissionAmount": owner_commission_amount,
        "dividendPoolAmount": dividend_pool_amount,
        "dividendPerMemberAmount": dividend_per_member_amount,
        "winnerPayoutAmount": winner_payout_amount,
    }


def _create_or_update_minimal_auction_result(
    db: Session,
    *,
    session: AuctionSession,
    winning_bid: AuctionBid,
    winner_membership_id: int,
    finalized_by_user_id: int,
    finalized_at: datetime,
    payout_snapshot: dict[str, int],
    existing_result: AuctionResult | None = None,
) -> AuctionResult:
    result = existing_result
    if result is None:
        result = AuctionResult(
            auction_session_id=session.id,
            group_id=session.group_id,
            cycle_no=session.cycle_no,
            winner_membership_id=winner_membership_id,
            winning_bid_id=winning_bid.id,
            winning_bid_amount=winning_bid.bid_amount,
            dividend_pool_amount=payout_snapshot["dividendPoolAmount"],
            dividend_per_member_amount=payout_snapshot["dividendPerMemberAmount"],
            owner_commission_amount=payout_snapshot["ownerCommissionAmount"],
            winner_payout_amount=payout_snapshot["winnerPayoutAmount"],
            finalized_by_user_id=finalized_by_user_id,
            finalized_at=finalized_at,
        )
        db.add(result)
    else:
        result.group_id = session.group_id
        result.cycle_no = session.cycle_no
        result.winner_membership_id = winner_membership_id
        result.winning_bid_id = winning_bid.id
        result.winning_bid_amount = winning_bid.bid_amount
        result.dividend_pool_amount = payout_snapshot["dividendPoolAmount"]
        result.dividend_per_member_amount = payout_snapshot["dividendPerMemberAmount"]
        result.owner_commission_amount = payout_snapshot["ownerCommissionAmount"]
        result.winner_payout_amount = payout_snapshot["winnerPayoutAmount"]
        result.finalized_by_user_id = finalized_by_user_id
        result.finalized_at = finalized_at

    db.flush()
    return result


def _select_winning_bid_for_finalize(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    effective_now: datetime,
) -> tuple[AuctionBid | None, int | None]:
    if is_fixed_auction(session):
        winner_membership = _get_fixed_mode_winner_membership(db, session)
        if winner_membership is None:
            return None, None
        winning_bid = _get_or_create_fixed_mode_bid(
            db,
            session=session,
            membership=winner_membership,
            placed_at=effective_now,
        )
        return winning_bid, winner_membership.id

    winning_bid = select_winning_bid(db, session.id)
    if winning_bid is None:
        return None, None
    return winning_bid, winning_bid.membership_id


def _should_queue_finalize_post_processing(db: Session, result: AuctionResult | None) -> bool:
    if result is None:
        return False
    payout_id = db.scalar(select(Payout.id).where(Payout.auction_result_id == result.id))
    return payout_id is None


def _dispatch_finalize_post_processing_task(session_id: int) -> None:
    dispatch_started_at = perf_counter()
    _log_finalize_trace(
        "STEP: finalize_post_processing.delay",
        session_id=int(session_id),
        step="finalize_post_processing.delay",
    )
    try:
        from app.tasks.auction_tasks import finalize_post_processing

        finalize_post_processing.delay(int(session_id))
        _log_finalize_trace(
            "STEP DONE: finalize_post_processing.delay",
            session_id=int(session_id),
            step="finalize_post_processing.delay",
            duration_ms=(perf_counter() - dispatch_started_at) * 1000,
        )
        logger.info(
            "Finalize post-processing task dispatched",
            extra={
                "event": "auction.finalize.task.dispatched",
                "auction_session_id": int(session_id),
            },
        )
    except Exception:
        logger.exception(
            "Finalize post-processing task dispatch failed",
            extra={
                "event": "auction.finalize.task.dispatch_failed",
                "auction_session_id": int(session_id),
            },
        )


def _dispatch_finalize_post_processing_task_nonblocking(session_id: int) -> None:
    if _finalize_task_executes_inline():
        _dispatch_finalize_post_processing_task(session_id)
        return

    Thread(
        target=_dispatch_finalize_post_processing_task,
        args=(int(session_id),),
        daemon=True,
        name=f"auction-finalize-dispatch-{int(session_id)}",
    ).start()


def _finalize_job_timeout_cutoff(now: datetime | None = None) -> datetime:
    return _normalize_datetime(now or utcnow()) - timedelta(seconds=int(settings.finalize_job_processing_timeout_seconds))


def _truncate_finalize_job_error(exc: Exception | str) -> str:
    text_value = str(exc).strip() or exc.__class__.__name__ if isinstance(exc, Exception) else str(exc).strip()
    if len(text_value) <= FINALIZE_JOB_ERROR_LIMIT:
        return text_value
    return text_value[: FINALIZE_JOB_ERROR_LIMIT - 3] + "..."


def _mark_finalize_job_stuck_or_failed(
    db: Session,
    *,
    job: FinalizeJob,
    error_message: str,
) -> str:
    max_retries = int(settings.finalize_job_max_retries)
    next_retry_count = int(job.retry_count or 0) + 1
    job.retry_count = next_retry_count
    job.last_error = _truncate_finalize_job_error(error_message)
    job.updated_at = utcnow()
    job.status = "failed" if next_retry_count >= max_retries else "pending"
    db.flush()
    return job.status


def _reset_stuck_finalize_jobs(
    db: Session,
    *,
    auction_id: int | None = None,
) -> list[int]:
    cutoff = _finalize_job_timeout_cutoff()
    statement = select(FinalizeJob).where(
        FinalizeJob.status == "processing",
        FinalizeJob.updated_at < cutoff,
    )
    if auction_id is not None:
        statement = statement.where(FinalizeJob.auction_id == auction_id)

    stuck_jobs = db.scalars(statement.order_by(FinalizeJob.updated_at.asc(), FinalizeJob.id.asc())).all()
    reset_job_ids: list[int] = []
    for job in stuck_jobs:
        status_value = _mark_finalize_job_stuck_or_failed(
            db,
            job=job,
            error_message="Finalize job exceeded processing timeout",
        )
        reset_job_ids.append(job.id)
        logger.warning(
            "Finalize job recovered from stuck processing state",
            extra={
                "event": "auction.finalize.job.stuck_reset",
                "finalize_job_id": job.id,
                "auction_session_id": job.auction_id,
                "status": status_value,
                "retry_count": job.retry_count,
            },
        )
    if reset_job_ids:
        db.commit()
    return reset_job_ids


def _raise_if_finalize_request_timed_out(started_at: float) -> None:
    elapsed_seconds = perf_counter() - started_at
    if elapsed_seconds <= float(settings.finalize_request_timeout_seconds):
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Auction finalize timed out before completion",
    )


def _raise_if_finalize_job_timed_out(started_at: float, *, session_id: int) -> None:
    elapsed_seconds = perf_counter() - started_at
    if elapsed_seconds <= float(settings.finalize_job_time_limit_seconds):
        return
    raise RuntimeError(f"Finalize post-processing timed out for auction session {session_id}")


def ensure_finalize_job_enqueued(db: Session, auction_id: int) -> FinalizeJob:
    step_started_at = perf_counter()
    _log_finalize_trace(
        "STEP: ensure_finalize_job_enqueued",
        session_id=int(auction_id),
        step="ensure_finalize_job_enqueued",
    )
    job = db.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == auction_id))
    now = utcnow()
    if job is None:
        try:
            with db.begin_nested():
                job = FinalizeJob(
                    auction_id=int(auction_id),
                    status="pending",
                    retry_count=0,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(job)
                db.flush()
        except IntegrityError:
            job = db.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == auction_id))
            if job is None:
                raise
        else:
            logger.info(
                "Finalize job enqueued",
                extra={
                    "event": "auction.finalize.job.enqueued",
                    "auction_session_id": auction_id,
                    "finalize_job_id": job.id,
                    "status": job.status,
                },
            )
            _log_finalize_trace(
                "STEP DONE: ensure_finalize_job_enqueued",
                session_id=int(auction_id),
                step="ensure_finalize_job_enqueued",
                duration_ms=(perf_counter() - step_started_at) * 1000,
                finalize_job_id=job.id,
                finalize_job_status=job.status,
            )
            return job

    if job is None:
        raise RuntimeError("Finalize job could not be loaded")

    if job.status in {"done", "failed"}:
        job.status = "pending"
        job.last_error = None
        job.updated_at = now
        logger.info(
            "Finalize job requeued",
            extra={
                "event": "auction.finalize.job.requeued",
                "auction_session_id": auction_id,
                "finalize_job_id": job.id,
                "retry_count": job.retry_count,
            },
        )
    _log_finalize_trace(
        "STEP DONE: ensure_finalize_job_enqueued",
        session_id=int(auction_id),
        step="ensure_finalize_job_enqueued",
        duration_ms=(perf_counter() - step_started_at) * 1000,
        finalize_job_id=job.id,
        finalize_job_status=job.status,
        retry_count=int(job.retry_count or 0),
    )
    return job


def _claim_finalize_job(
    db: Session,
    *,
    auction_id: int | None = None,
) -> FinalizeJob | None:
    _reset_stuck_finalize_jobs(db, auction_id=auction_id)
    statement = select(FinalizeJob).where(FinalizeJob.status == "pending")
    if auction_id is not None:
        statement = statement.where(FinalizeJob.auction_id == auction_id)
    job = db.scalar(statement.order_by(FinalizeJob.created_at.asc(), FinalizeJob.id.asc()).limit(1))
    if job is None:
        return None

    claimed = db.execute(
        update(FinalizeJob)
        .where(
            FinalizeJob.id == job.id,
            FinalizeJob.status == "pending",
        )
        .values(
            status="processing",
            last_error=None,
            updated_at=utcnow(),
        )
    )
    if int(claimed.rowcount or 0) != 1:
        db.rollback()
        return None

    db.flush()
    claimed_job = db.get(FinalizeJob, job.id)
    if claimed_job is not None:
        logger.info(
            "job picked",
            extra={
                "event": "auction.finalize.job.claimed",
                "finalize_job_id": claimed_job.id,
                "auction_session_id": claimed_job.auction_id,
                "retry_count": claimed_job.retry_count,
            },
        )
    return claimed_job


def _ensure_winner_membership_prized(
    db: Session,
    *,
    membership: GroupMembership,
    cycle_no: int,
) -> None:
    if membership.prized_status == "prized" and membership.prized_cycle_no == cycle_no:
        return

    try:
        mark_membership_slot_won(db, membership, cycle_no=cycle_no)
    except ValueError:
        db.refresh(membership)
        slot_summary = build_membership_slot_summary(db, membership)
        if not slot_summary.has_any_won:
            raise
        membership.prized_status = "prized"
        membership.prized_cycle_no = cycle_no
        membership.can_bid = False
    membership.updated_at = utcnow()
    db.flush()


def _run_finalize_post_processing(
    db: Session,
    *,
    session_id: int,
) -> dict[str, int | bool]:
    started_at = perf_counter()
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    _raise_if_finalize_job_timed_out(started_at, session_id=session_id)

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")
    _raise_if_finalize_job_timed_out(started_at, session_id=session_id)

    owner = db.get(Owner, group.owner_id)
    owner_user = db.get(User, owner.user_id) if owner is not None else None
    owner_current_user = (
        CurrentUser(user=owner_user, owner=owner, subscriber=None)
        if owner is not None and owner_user is not None
        else None
    )

    result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    if session.status != "finalized" or result is None:
        finalized_by_user_id = session.closed_by_user_id or (owner_user.id if owner_user is not None else None)
        if finalized_by_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Auction session cannot be finalized without an owning owner",
            )
        _finalize_loaded_auction_session(
            db,
            session=session,
            group=group,
            finalized_by_user_id=finalized_by_user_id,
            current_user=owner_current_user,
            actor_user_id=finalized_by_user_id,
            publish_events=True,
            enqueue_post_processing=False,
            enforce_request_timeout=False,
        )
        session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
        result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
        if result is None:
            return {
                "sessionId": session_id,
                "hasResult": False,
                "processed": True,
            }

    logger.info(
        "Auction finalize post-processing started",
        extra={
            "event": "auction.finalize.post_processing.start",
            "auction_session_id": session.id,
            "group_id": group.id,
        },
    )

    try:
        winner_membership = db.scalar(
            select(GroupMembership).where(
                GroupMembership.id == result.winner_membership_id,
                GroupMembership.group_id == session.group_id,
            )
        )
        if winner_membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Winner membership not found")

        _ensure_winner_membership_prized(db, membership=winner_membership, cycle_no=session.cycle_no)
        if int(group.current_cycle_no or 1) <= int(session.cycle_no):
            _advance_group_cycle(group, session)
        _raise_if_finalize_job_timed_out(started_at, session_id=session_id)

        payout_result = ensure_auction_payout(
            db,
            result=result,
            group=group,
            membership=winner_membership,
        )
        payout = payout_result[0] if isinstance(payout_result, tuple) else payout_result
        _raise_if_finalize_job_timed_out(started_at, session_id=session_id)
        winner_subscriber = db.get(Subscriber, winner_membership.subscriber_id)
        notify_auction_finalized(
            db,
            session=session,
            result=result,
            group=group,
            owner=db.get(Owner, group.owner_id),
            winner_membership=winner_membership,
            winner_subscriber=winner_subscriber,
        )
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "Auction finalize post-processing completed",
            extra={
                "event": "auction.finalize.post_processing.completed",
                "auction_session_id": session.id,
                "group_id": group.id,
                "duration_ms": duration_ms,
                "payout_id": getattr(payout, "id", None),
            },
        )
        return {
            "sessionId": session.id,
            "auctionResultId": result.id,
            "payoutId": getattr(payout, "id", None),
            "processed": True,
        }
    except Exception:
        logger.exception(
            "Auction finalize post-processing failed",
            extra={
                "event": "auction.finalize.post_processing.failed",
                "auction_session_id": session.id,
                "group_id": group.id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise


def finalize_auction_post_processing(
    db: Session,
    *,
    session_id: int,
) -> dict[str, int | bool]:
    try:
        result = _run_finalize_post_processing(db, session_id=session_id)
        db.commit()
        dispatch_staged_notifications(db)
        return result
    except Exception:
        db.rollback()
        logger.exception(
            "Auction finalize post-processing failed",
            extra={
                "event": "auction.finalize.post_processing.failed",
                "auction_session_id": session_id,
            },
        )
        raise


def process_pending_finalize_jobs(
    db: Session,
    *,
    limit: int | None = None,
    auction_id: int | None = None,
) -> list[dict[str, int | bool]]:
    processed_jobs: list[dict[str, int | bool]] = []
    max_jobs = max(int(limit or 10), 1)

    for _ in range(max_jobs):
        job = _claim_finalize_job(db, auction_id=auction_id)
        if job is None:
            if not processed_jobs:
                logger.info(
                    "Finalize job worker idle",
                    extra={
                        "event": "auction.finalize.job.idle",
                        "auction_session_id": auction_id,
                    },
                )
            break

        try:
            result = _run_finalize_post_processing(db, session_id=job.auction_id)
            job.status = "done"
            job.last_error = None
            job.updated_at = utcnow()
            db.flush()
            db.commit()
            dispatch_staged_notifications(db)
            payload = {
                "jobId": job.id,
                "auctionId": job.auction_id,
                "retryCount": int(job.retry_count or 0),
                **result,
            }
            processed_jobs.append(payload)
            logger.info(
                "job completed",
                extra={
                    "event": "auction.finalize.job.completed",
                    "finalize_job_id": job.id,
                    "auction_session_id": job.auction_id,
                    "retry_count": job.retry_count,
                },
            )
        except Exception as exc:
            db.rollback()
            job = db.get(FinalizeJob, job.id)
            if job is not None:
                status_value = _mark_finalize_job_stuck_or_failed(
                    db,
                    job=job,
                    error_message="Finalize job failed: " + _truncate_finalize_job_error(exc),
                )
                db.commit()
                logger.exception(
                    "Finalize job processing failed",
                    extra={
                        "event": "auction.finalize.job.retry" if status_value != "failed" else "auction.finalize.job.failed",
                        "auction_session_id": job.auction_id,
                        "finalize_job_id": job.id,
                        "retry_count": job.retry_count,
                        "status": status_value,
                        "last_error": job.last_error,
                    },
                )
                if status_value != "failed":
                    continue
            logger.exception(
                "Finalize job processing failed",
                extra={
                    "event": "auction.finalize.job.failed",
                    "auction_session_id": job.auction_id,
                    "finalize_job_id": job.id,
                },
            )
            if auction_id is not None:
                break

        if auction_id is not None:
            break

    return processed_jobs


def reconcile_incomplete_auctions(
    db: Session,
    *,
    limit: int | None = None,
) -> dict[str, object]:
    max_repairs = max(int(limit or 25), 1)
    repaired_auction_ids: list[int] = []
    repaired_payment_ids: list[int] = []
    repaired_installment_ids: list[int] = []

    session_ids = db.scalars(
        select(AuctionSession.id)
        .join(AuctionResult, AuctionResult.auction_session_id == AuctionSession.id)
        .outerjoin(Payout, Payout.auction_result_id == AuctionResult.id)
        .outerjoin(
            LedgerEntry,
            and_(
                LedgerEntry.source_table == "payouts",
                LedgerEntry.source_id == Payout.id,
            ),
        )
        .where(
            AuctionSession.status == "finalized",
            or_(Payout.id.is_(None), LedgerEntry.id.is_(None)),
        )
        .order_by(AuctionSession.id.asc())
        .limit(max_repairs)
    ).all()

    for session_id in session_ids:
        try:
            result = _run_finalize_post_processing(db, session_id=int(session_id))
            db.commit()
            dispatch_staged_notifications(db)
            if result.get("processed"):
                repaired_auction_ids.append(int(session_id))
        except Exception:
            db.rollback()
            logger.exception(
                "Auction reconciliation failed",
                extra={
                    "event": "auction.finalize.reconcile.failed",
                    "auction_session_id": int(session_id),
                },
            )

    payments_missing_ledger = db.scalars(
        select(Payment)
        .outerjoin(
            LedgerEntry,
            and_(
                LedgerEntry.source_table == "payments",
                LedgerEntry.source_id == Payment.id,
            ),
        )
        .where(
            Payment.status == "recorded",
            LedgerEntry.id.is_(None),
        )
        .order_by(Payment.id.asc())
        .limit(max_repairs)
    ).all()
    for payment in payments_missing_ledger:
        ensure_payment_ledger_entry(db, payment)
        repaired_payment_ids.append(payment.id)
    if payments_missing_ledger:
        db.commit()

    installment_ids = db.scalars(
        select(Payment.installment_id)
        .where(
            Payment.status == "recorded",
            Payment.installment_id.is_not(None),
        )
        .distinct()
        .order_by(Payment.installment_id.asc())
        .limit(max_repairs)
    ).all()
    for installment_id in installment_ids:
        installment = db.get(Installment, int(installment_id))
        if installment is None:
            continue
        before_state = (
            money_int(installment.paid_amount),
            money_int(installment.balance_amount),
            money_int(installment.penalty_amount),
            installment.status,
        )
        rebuilt = rebuild_installment_from_payments(
            db,
            installment,
            db.get(ChitGroup, installment.group_id),
            commit=False,
        )
        after_state = (
            money_int(rebuilt.paid_amount),
            money_int(rebuilt.balance_amount),
            money_int(rebuilt.penalty_amount),
            rebuilt.status,
        )
        if before_state != after_state:
            repaired_installment_ids.append(rebuilt.id)
    if repaired_installment_ids:
        db.commit()

    return {
        "repairedAuctionIds": repaired_auction_ids,
        "repairedPaymentIds": repaired_payment_ids,
        "repairedInstallmentIds": repaired_installment_ids,
    }


def _finalize_loaded_auction_session(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    finalized_by_user_id: int,
    current_user: CurrentUser | None = None,
    actor_user_id: int | None = None,
    publish_events: bool = True,
    enqueue_post_processing: bool = True,
    enforce_request_timeout: bool = True,
    now_override: datetime | None = None,
) -> dict:
    started_at = perf_counter()

    def _log_finalize_step(step: str, step_started_at: float) -> None:
        logger.info(
            "Auction finalization step completed",
            extra={
                "event": "auction.finalize.step",
                "auction_session_id": session.id,
                "group_id": group.id,
                "step": step,
                "duration_ms": round((perf_counter() - step_started_at) * 1000, 2),
            },
        )
        if enforce_request_timeout:
            _raise_if_finalize_request_timed_out(started_at)

    logger.info(
        "Auction finalization started",
        extra={
            "event": "auction.finalize.started",
            "auction_session_id": session.id,
            "group_id": group.id,
        },
    )

    try:
        effective_now = now_override or utcnow()

        load_started_at = perf_counter()
        _log_finalize_trace(
            "STEP: loading session",
            session_id=session.id,
            group_id=group.id,
            step="loading-session",
        )
        step_started_at = perf_counter()
        existing_result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
        _log_finalize_trace(
            "STEP: selecting bids",
            session_id=session.id,
            group_id=group.id,
            step="selecting-bids",
        )
        total_bid_count, valid_bid_count = _get_bid_count_snapshot(db, session.id)
        _log_finalize_trace(
            "STEP DONE: selecting bids",
            session_id=session.id,
            group_id=group.id,
            step="selecting-bids",
            duration_ms=(perf_counter() - step_started_at) * 1000,
            total_bid_count=int(total_bid_count),
            valid_bid_count=int(valid_bid_count),
        )
        audit_before = _serialize_auction_audit_state(session, existing_result)
        _log_finalize_trace(
            "STEP DONE: loading session",
            session_id=session.id,
            group_id=group.id,
            step="loading-session",
            duration_ms=(perf_counter() - load_started_at) * 1000,
            session_status=session.status,
            existing_result_id=existing_result.id if existing_result is not None else None,
        )
        _log_finalize_step("load-state", step_started_at)

        if session.status not in {"open", "closed", "finalizing", "finalized"}:
            raise RuntimeError("INVALID_STATE")
        if session.status == "finalized":
            winner_details = _get_membership_display_details_joined(
                db,
                existing_result.winner_membership_id if existing_result is not None else None,
            )
            if enqueue_post_processing and _should_queue_finalize_post_processing(db, existing_result):
                enqueue_started_at = perf_counter()
                ensure_finalize_job_enqueued(db, session.id)
                _log_finalize_trace(
                    "STEP: DB commit",
                    session_id=session.id,
                    group_id=group.id,
                    step="db-commit-finalize-job",
                )
                db.commit()
                _log_finalize_trace(
                    "STEP DONE: DB commit",
                    session_id=session.id,
                    group_id=group.id,
                    step="db-commit-finalize-job",
                    duration_ms=(perf_counter() - enqueue_started_at) * 1000,
                )
                _dispatch_finalize_post_processing_task(session.id)
            step_started_at = perf_counter()
            response = _build_finalization_response(
                db,
                session=session,
                group=group,
                result=existing_result,
                current_user=current_user,
                fallback_finalized_by_user_id=finalized_by_user_id,
                total_bids=total_bid_count,
                valid_bid_count=valid_bid_count,
                winner_details=winner_details,
                finalized_by_name=(
                    current_user.owner.display_name
                    if current_user is not None and current_user.owner is not None
                    else None
                ),
            )
            _log_finalize_step("response-returned", step_started_at)
            return response
        if (
            existing_result is None
            and session.status != "finalizing"
            and not can_finalize_auction_session(db, session, now=effective_now)
        ):
            raise RuntimeError("INVALID_STATE")

        result = existing_result
        winning_bid: AuctionBid | None = None
        winner_membership_id: int | None = None
        payout_snapshot: dict[str, int] | None = None
        winner_details = _get_membership_display_details_joined(
            db,
            result.winner_membership_id if result is not None else None,
        ) if result is not None else None
        if result is None:
            step_started_at = perf_counter()
            _log_finalize_trace(
                "STEP: selecting winner",
                session_id=session.id,
                group_id=group.id,
                step="selecting-winner",
                total_bid_count=int(total_bid_count),
                valid_bid_count=int(valid_bid_count),
                auction_mode=get_auction_mode(session),
            )
            winning_bid, winner_membership_id = _select_winning_bid_for_finalize(
                db,
                session=session,
                group=group,
                effective_now=effective_now,
            )
            if winning_bid is not None and winner_membership_id is not None:
                payout_snapshot = _build_minimal_payout_snapshot(
                    session=session,
                    group=group,
                    winning_bid_amount=money_int(winning_bid.bid_amount),
                )
                if is_fixed_auction(session) and total_bid_count == 0:
                    total_bid_count = 1
                    valid_bid_count = 1
                winner_details = _get_membership_display_details_joined(db, winner_membership_id)
            _log_finalize_trace(
                "STEP DONE: selecting winner",
                session_id=session.id,
                group_id=group.id,
                step="selecting-winner",
                duration_ms=(perf_counter() - step_started_at) * 1000,
                winning_bid_id=winning_bid.id if winning_bid is not None else None,
                winner_membership_id=winner_membership_id,
            )
            _log_finalize_step("winner-selected", step_started_at)

        step_started_at = perf_counter()
        _log_finalize_trace(
            "STEP: DB transaction begin",
            session_id=session.id,
            group_id=group.id,
            step="db-transaction-begin",
        )
        session.status = "finalized"
        if session.closed_by_user_id is None:
            session.closed_by_user_id = finalized_by_user_id
        if session.actual_end_at is None:
            session.actual_end_at = effective_now
        if winning_bid is not None:
            session.winning_bid_id = winning_bid.id
        session.updated_at = effective_now

        if result is None and winning_bid is not None and winner_membership_id is not None and payout_snapshot is not None:
            result = _create_or_update_minimal_auction_result(
                db,
                session=session,
                winning_bid=winning_bid,
                winner_membership_id=winner_membership_id,
                finalized_by_user_id=finalized_by_user_id,
                finalized_at=effective_now,
                payout_snapshot=payout_snapshot,
            )
            _log_finalize_step("result-created", step_started_at)
        else:
            db.flush()
            _log_finalize_step("mark-finalized", step_started_at)
        _log_finalize_trace(
            "STEP DONE: DB transaction begin",
            session_id=session.id,
            group_id=group.id,
            step="db-transaction-begin",
            duration_ms=(perf_counter() - step_started_at) * 1000,
            result_id=result.id if result is not None else None,
        )

        step_started_at = perf_counter()
        log_audit_event(
            db,
            action="auction.finalized",
            entity_type="auction_session",
            entity_id=session.id,
            current_user=current_user,
            actor_user_id=actor_user_id if actor_user_id is not None else finalized_by_user_id,
            owner_id=group.owner_id,
            metadata={
                "auctionSessionId": session.id,
                "cycleNo": session.cycle_no,
                "winningBidId": result.winning_bid_id if result is not None else session.winning_bid_id,
            },
            before=audit_before,
            after=_serialize_auction_audit_state(session, result),
        )
        _log_finalize_step("audit-recorded", step_started_at)

        step_started_at = perf_counter()
        _log_finalize_trace(
            "STEP: DB commit",
            session_id=session.id,
            group_id=group.id,
            step="db-commit-finalize",
        )
        db.commit()
        _log_finalize_trace(
            "STEP DONE: DB commit",
            session_id=session.id,
            group_id=group.id,
            step="db-commit-finalize",
            duration_ms=(perf_counter() - step_started_at) * 1000,
        )
        _log_finalize_step("commit", step_started_at)

        if enqueue_post_processing and _should_queue_finalize_post_processing(db, result):
            enqueue_started_at = perf_counter()
            ensure_finalize_job_enqueued(db, session.id)
            _log_finalize_trace(
                "STEP: DB commit",
                session_id=session.id,
                group_id=group.id,
                step="db-commit-finalize-job",
            )
            db.commit()
            _log_finalize_trace(
                "STEP DONE: DB commit",
                session_id=session.id,
                group_id=group.id,
                step="db-commit-finalize-job",
                duration_ms=(perf_counter() - enqueue_started_at) * 1000,
            )
            _dispatch_finalize_post_processing_task(session.id)

        step_started_at = perf_counter()
        response = _build_finalization_response(
            db,
            session=session,
            group=group,
            result=result,
            current_user=current_user,
            fallback_finalized_by_user_id=finalized_by_user_id,
            total_bids=total_bid_count,
            valid_bid_count=valid_bid_count,
            winner_details=winner_details,
            finalized_by_name=(
                current_user.owner.display_name
                if current_user is not None and current_user.owner is not None
                else None
            ),
        )
        _log_finalize_step("response-returned", step_started_at)

        if publish_events and response["console"] is not None:
            step_started_at = perf_counter()
            publish_auction_finalize_event(
                session.id,
                {
                    "console": response["console"],
                },
            )
            _log_finalize_step("publish-events", step_started_at)
        return response
    except Exception:
        db.rollback()
        logger.exception(
            "Auction finalization failed",
            extra={
                "event": "auction.finalize.failed",
                "auction_session_id": session.id,
                "group_id": group.id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    finally:
        logger.info(
            "Auction finalization completed",
            extra={
                "event": "auction.finalize.completed",
                "auction_session_id": session.id,
                "group_id": group.id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )


def _build_finalization_response(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    result: AuctionResult | None,
    current_user: CurrentUser | None,
    fallback_finalized_by_user_id: int,
    total_bids: int | None = None,
    valid_bid_count: int | None = None,
    winner_details: dict[str, int | str | None] | None = None,
    finalized_by_name: str | None = None,
) -> dict:
    resolved_total_bids = int(total_bids) if total_bids is not None else (
        db.scalar(select(func.count(AuctionBid.id)).where(AuctionBid.auction_session_id == session.id)) or 0
    )
    resolved_valid_bid_count = int(valid_bid_count) if valid_bid_count is not None else _get_valid_bid_count(db, session.id)
    finalized_by_user_id = result.finalized_by_user_id if result is not None else (
        session.closed_by_user_id or fallback_finalized_by_user_id
    )
    resolved_finalized_by_name = finalized_by_name or (
        current_user.owner.display_name
        if current_user is not None
        and current_user.owner is not None
        and current_user.user.id == finalized_by_user_id
        else _get_user_display_name(db, finalized_by_user_id)
    )
    resolved_winner_details = winner_details or _get_membership_display_details_joined(
        db,
        result.winner_membership_id if result is not None else None,
    )
    winner_name = resolved_winner_details["winnerName"]
    winner_membership_id = resolved_winner_details["winnerMembershipId"]
    winner_membership_no = resolved_winner_details["winnerMembershipNo"]
    winning_bid_amount = money_int(result.winning_bid_amount) if result is not None else None
    console_snapshot = None
    if current_user is not None and current_user.owner is not None:
        console_snapshot = {
            "sessionId": session.id,
            "groupTitle": group.title,
            "groupCode": group.group_code,
            "auctionMode": get_auction_mode(session),
            "commissionMode": (session.commission_mode or "NONE").upper(),
            "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
            "minBidValue": _normalize_bid_control_value(session.min_bid_value, fallback=DEFAULT_MIN_BID_VALUE),
            "maxBidValue": _normalize_bid_control_value(session.max_bid_value, fallback=money_int(group.chit_value)),
            "minIncrement": _normalize_bid_control_value(session.min_increment, fallback=DEFAULT_MIN_INCREMENT),
            "auctionState": get_auction_state(session, now=utcnow(), has_result=result is not None),
            "cycleNo": session.cycle_no,
            "status": session.status,
            "scheduledStartAt": session.scheduled_start_at,
            "actualStartAt": session.actual_start_at,
            "actualEndAt": session.actual_end_at,
            "startTime": session.start_time,
            "endTime": session.end_time,
            "serverTime": utcnow(),
            "totalBidCount": resolved_total_bids,
            "validBidCount": resolved_valid_bid_count,
            "highestBidAmount": winning_bid_amount,
            "highestBidMembershipNo": winner_membership_no,
            "highestBidderName": winner_name,
            "canFinalize": False,
            "auctionResultId": result.id if result else None,
            "finalizedAt": result.finalized_at if result else session.updated_at if session.status == "finalized" else None,
            "finalizedByName": resolved_finalized_by_name,
            "winnerMembershipId": winner_membership_id,
            "winnerMembershipNo": winner_membership_no,
            "winnerName": winner_name,
            "winningBidId": result.winning_bid_id if result else session.winning_bid_id,
            "winningBidAmount": winning_bid_amount,
            "ownerCommissionAmount": money_int(result.owner_commission_amount) if result else None,
            "dividendPoolAmount": money_int(result.dividend_pool_amount) if result else None,
            "dividendPerMemberAmount": money_int(result.dividend_per_member_amount) if result else None,
            "winnerPayoutAmount": money_int(result.winner_payout_amount) if result else None,
            "finalizationMessage": _get_no_bid_finalization_message(
                session=session,
                result=result,
                valid_bid_count=resolved_valid_bid_count,
            ),
        }

    return {
        "sessionId": session.id,
        "groupId": group.id,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "cycleNo": session.cycle_no,
        "status": session.status,
        "closedAt": session.actual_end_at,
        "finalizedAt": result.finalized_at if result is not None else session.updated_at,
        "closedByUserId": session.closed_by_user_id,
        "finalizedByUserId": finalized_by_user_id,
        "finalizedByName": resolved_finalized_by_name,
        "finalizationMessage": _get_no_bid_finalization_message(
            session=session,
            result=result,
            valid_bid_count=resolved_valid_bid_count,
        ),
        "resultSummary": {
            "sessionId": session.id,
            "status": session.status,
            "totalBids": resolved_total_bids,
            "validBidCount": resolved_valid_bid_count,
            "auctionResultId": result.id if result is not None else None,
            "winnerMembershipId": winner_membership_id,
            "winnerMembershipNo": winner_membership_no,
            "winnerName": winner_name,
            "winningBidId": result.winning_bid_id if result is not None else None,
            "winningBidAmount": winning_bid_amount,
            "ownerCommissionAmount": money_int(result.owner_commission_amount) if result is not None else None,
            "dividendPoolAmount": money_int(result.dividend_pool_amount) if result is not None else None,
            "dividendPerMemberAmount": money_int(result.dividend_per_member_amount) if result is not None else None,
            "winnerPayoutAmount": money_int(result.winner_payout_amount) if result is not None else None,
        },
        "console": console_snapshot,
    }


def _advance_group_cycle(group: ChitGroup, session: AuctionSession) -> None:
    is_terminal_cycle = session.cycle_no >= group.cycle_count
    group.current_cycle_no = min(session.cycle_no + 1, group.cycle_count)
    group.bidding_enabled = not is_terminal_cycle
    group.status = "completed" if is_terminal_cycle else "active"
    group.updated_at = utcnow()


def _get_owner_session(
    db: Session,
    session_id: int,
    current_user: CurrentUser,
    *,
    for_update: bool = False,
) -> tuple[AuctionSession, ChitGroup]:
    owner = require_owner(current_user)
    statement = (
        select(AuctionSession, ChitGroup)
        .join(ChitGroup, ChitGroup.id == AuctionSession.group_id)
        .where(AuctionSession.id == session_id)
    )
    if for_update:
        statement = statement.with_for_update()
    row = db.execute(statement).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    session, group = row
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot finalize another owner's auction")
    return session, group


def _build_result_summary(db: Session, session: AuctionSession, result: AuctionResult | None) -> dict:
    total_bids = db.scalar(
        select(func.count(AuctionBid.id)).where(AuctionBid.auction_session_id == session.id)
    ) or 0
    valid_bid_count = _get_valid_bid_count(db, session.id)
    winner_details = _get_membership_display_details(
        db,
        result.winner_membership_id if result is not None else None,
    )

    summary = {
        "sessionId": session.id,
        "status": session.status,
        "totalBids": int(total_bids),
        "validBidCount": int(valid_bid_count),
        "auctionResultId": result.id if result is not None else None,
        "winnerMembershipId": winner_details["winnerMembershipId"],
        "winnerMembershipNo": winner_details["winnerMembershipNo"],
        "winnerName": winner_details["winnerName"],
        "winningBidId": result.winning_bid_id if result else session.winning_bid_id,
        "winningBidAmount": money_int(result.winning_bid_amount) if result else None,
        "ownerCommissionAmount": money_int(result.owner_commission_amount) if result else None,
        "dividendPoolAmount": money_int(result.dividend_pool_amount) if result else None,
        "dividendPerMemberAmount": money_int(result.dividend_per_member_amount) if result else None,
        "winnerPayoutAmount": money_int(result.winner_payout_amount) if result else None,
    }
    return summary


def _build_enqueued_finalize_response(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    current_user: CurrentUser,
) -> dict | None:
    finalized_by_user_id = session.closed_by_user_id or current_user.user.id
    finalized_by_name = (
        current_user.owner.display_name
        if current_user.owner is not None
        else _get_user_display_name(db, finalized_by_user_id)
    )
    queued_at = session.updated_at or utcnow()
    is_already_finalized = session.status == "finalized"
    finalization_message = (
        "Auction closed and finalized."
        if is_already_finalized
        else "Auction finalization queued."
    )
    console_snapshot = {
        "sessionId": session.id,
        "groupTitle": group.title,
        "groupCode": group.group_code,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "minBidValue": _normalize_bid_control_value(session.min_bid_value, fallback=DEFAULT_MIN_BID_VALUE),
        "maxBidValue": _normalize_bid_control_value(session.max_bid_value, fallback=money_int(group.chit_value)),
        "minIncrement": _normalize_bid_control_value(session.min_increment, fallback=DEFAULT_MIN_INCREMENT),
        "auctionState": get_auction_state(session, now=queued_at, has_result=is_already_finalized),
        "cycleNo": session.cycle_no,
        "status": session.status,
        "scheduledStartAt": session.scheduled_start_at,
        "actualStartAt": session.actual_start_at,
        "actualEndAt": session.actual_end_at,
        "startTime": session.start_time,
        "endTime": session.end_time,
        "serverTime": queued_at,
        "totalBidCount": 0,
        "validBidCount": 0,
        "highestBidAmount": None,
        "highestBidMembershipNo": None,
        "highestBidderName": None,
        "canFinalize": False,
        "auctionResultId": None,
        "finalizedAt": queued_at if is_already_finalized else None,
        "finalizedByName": finalized_by_name,
        "winnerMembershipId": None,
        "winnerMembershipNo": None,
        "winnerName": None,
        "winningBidId": session.winning_bid_id,
        "winningBidAmount": None,
        "ownerCommissionAmount": None,
        "dividendPoolAmount": None,
        "dividendPerMemberAmount": None,
        "winnerPayoutAmount": None,
        "finalizationMessage": finalization_message,
    }
    return {
        "sessionId": session.id,
        "groupId": group.id,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "cycleNo": session.cycle_no,
        "status": session.status,
        "closedAt": session.actual_end_at or queued_at,
        "finalizedAt": queued_at,
        "closedByUserId": session.closed_by_user_id,
        "finalizedByUserId": finalized_by_user_id,
        "finalizedByName": finalized_by_name,
        "finalizationMessage": finalization_message,
        "resultSummary": {
            "sessionId": session.id,
            "status": session.status,
            "totalBids": 0,
            "validBidCount": 0,
            "auctionResultId": None,
            "winnerMembershipId": None,
            "winnerMembershipNo": None,
            "winnerName": None,
            "winningBidId": session.winning_bid_id,
            "winningBidAmount": None,
            "ownerCommissionAmount": None,
            "dividendPoolAmount": None,
            "dividendPerMemberAmount": None,
            "winnerPayoutAmount": None,
        },
        "console": console_snapshot,
    }


def _recover_finalize_request_after_conflict(
    db: Session,
    *,
    session_id: int,
    current_user: CurrentUser,
) -> dict | None:
    try:
        session, group = _get_owner_session(db, session_id, current_user)
    except HTTPException:
        return None
    return _build_enqueued_finalize_response(
        db,
        session=session,
        group=group,
        current_user=current_user,
    )


def _finalize_task_executes_inline() -> bool:
    if "pytest" in sys.modules:
        return True
    try:
        from app.core.celery_app import celery_app

        return bool(getattr(celery_app.conf, "task_always_eager", False))
    except Exception:
        return False


def _build_inline_finalization_response(
    db: Session,
    *,
    session_id: int,
    current_user: CurrentUser,
) -> dict:
    session, group = _get_owner_session(db, session_id, current_user)
    result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    total_bid_count, valid_bid_count = _get_bid_count_snapshot(db, session.id)
    winner_details = _get_membership_display_details_joined(
        db,
        result.winner_membership_id if result is not None else None,
    )
    finalized_by_name = current_user.owner.display_name if current_user.owner is not None else None
    return _build_finalization_response(
        db,
        session=session,
        group=group,
        result=result,
        current_user=current_user,
        fallback_finalized_by_user_id=current_user.user.id,
        total_bids=total_bid_count,
        valid_bid_count=valid_bid_count,
        winner_details=winner_details,
        finalized_by_name=finalized_by_name,
    )


def _load_finalize_enqueue_context(
    db: Session,
    *,
    session_id: int,
    current_user: CurrentUser,
) -> FinalizeEnqueueContext:
    owner = require_owner(current_user)
    row = db.execute(
        text(
            """
            SELECT
                s.id AS session_id,
                s.group_id AS session_group_id,
                s.cycle_no,
                s.scheduled_start_at,
                s.actual_start_at,
                s.actual_end_at,
                s.start_time,
                s.end_time,
                s.auction_mode,
                s.commission_mode,
                s.commission_value,
                s.min_bid_value,
                s.max_bid_value,
                s.min_increment,
                s.bidding_window_seconds,
                s.status AS session_status,
                s.opened_by_user_id,
                s.closed_by_user_id,
                s.winning_bid_id AS session_winning_bid_id,
                s.updated_at AS session_updated_at,
                g.id AS group_id,
                g.owner_id AS group_owner_id,
                g.group_code,
                g.title,
                g.chit_value,
                g.installment_amount,
                g.member_count,
                g.cycle_count,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM auction_bids AS b
                        WHERE b.auction_session_id = s.id
                          AND b.is_valid IS TRUE
                    ) THEN 1
                    ELSE 0
                END AS has_valid_bid
            FROM auction_sessions AS s
            JOIN chit_groups AS g
                ON g.id = s.group_id
            WHERE s.id = :session_id
            LIMIT 1
            """
        ),
        {"session_id": int(session_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    if int(row["group_owner_id"]) != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot finalize another owner's auction")

    return FinalizeEnqueueContext(
        session=AuctionSessionSnapshot(
            id=int(row["session_id"]),
            group_id=int(row["session_group_id"]),
            cycle_no=int(row["cycle_no"]),
            scheduled_start_at=_coerce_datetime(row["scheduled_start_at"]),
            actual_start_at=_coerce_datetime(row["actual_start_at"]),
            actual_end_at=_coerce_datetime(row["actual_end_at"]),
            start_time=_coerce_datetime(row["start_time"]),
            end_time=_coerce_datetime(row["end_time"]),
            auction_mode=row["auction_mode"],
            commission_mode=row["commission_mode"],
            commission_value=row["commission_value"],
            min_bid_value=row["min_bid_value"],
            max_bid_value=row["max_bid_value"],
            min_increment=row["min_increment"],
            bidding_window_seconds=int(row["bidding_window_seconds"]),
            status=row["session_status"],
            opened_by_user_id=row["opened_by_user_id"],
            closed_by_user_id=row["closed_by_user_id"],
            winning_bid_id=row["session_winning_bid_id"],
            updated_at=_coerce_datetime(row["session_updated_at"]),
        ),
        group=ChitGroupSnapshot(
            id=int(row["group_id"]),
            owner_id=int(row["group_owner_id"]),
            group_code=row["group_code"],
            title=row["title"],
            chit_value=int(row["chit_value"]),
            installment_amount=int(row["installment_amount"]),
            member_count=int(row["member_count"]),
            cycle_count=int(row["cycle_count"]),
        ),
        has_valid_bid=bool(row["has_valid_bid"]),
    )


def _can_enqueue_finalize_request_from_context(
    *,
    session: AuctionSessionSnapshot,
    has_valid_bid: bool,
    current_time: datetime,
) -> bool:
    if session.status in {"finalizing", "finalized", "closed"}:
        return True
    if session.status != "open":
        return False
    if is_blind_auction(session) and current_time < get_auction_session_deadline(session):
        return False
    if get_auction_mode(session) == "FIXED":
        return True
    if has_valid_bid:
        return True
    return current_time >= get_auction_session_deadline(session)


def _persist_finalize_request_fast(
    db: Session,
    *,
    session_id: int,
    current_user_id: int,
    effective_now: datetime,
) -> None:
    dialect_name = db.get_bind().dialect.name
    params = {
        "session_id": int(session_id),
        "current_user_id": int(current_user_id),
        "effective_now": effective_now,
    }
    if dialect_name == "postgresql":
        db.execute(
            text(
                """
                WITH updated_session AS (
                    UPDATE auction_sessions
                    SET status = CASE
                            WHEN status IN ('finalizing', 'finalized') THEN status
                            ELSE 'finalizing'
                        END,
                        closed_by_user_id = COALESCE(closed_by_user_id, :current_user_id),
                        actual_end_at = COALESCE(actual_end_at, :effective_now),
                        updated_at = CASE
                            WHEN status IN ('finalizing', 'finalized') THEN updated_at
                            ELSE :effective_now
                        END
                    WHERE id = :session_id
                    RETURNING id
                )
                INSERT INTO finalize_jobs (
                    auction_id,
                    status,
                    retry_count,
                    last_error,
                    created_at,
                    updated_at
                )
                SELECT
                    :session_id,
                    'pending',
                    0,
                    NULL,
                    :effective_now,
                    :effective_now
                FROM updated_session
                ON CONFLICT (auction_id) DO UPDATE
                SET status = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN 'pending'
                        ELSE finalize_jobs.status
                    END,
                    last_error = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN NULL
                        ELSE finalize_jobs.last_error
                    END,
                    updated_at = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN EXCLUDED.updated_at
                        ELSE finalize_jobs.updated_at
                    END
                """
            ),
            params,
        )
        return

    if dialect_name == "sqlite":
        db.execute(
            text(
                """
                UPDATE auction_sessions
                SET status = CASE
                        WHEN status IN ('finalizing', 'finalized') THEN status
                        ELSE 'finalizing'
                    END,
                    closed_by_user_id = COALESCE(closed_by_user_id, :current_user_id),
                    actual_end_at = COALESCE(actual_end_at, :effective_now),
                    updated_at = CASE
                        WHEN status IN ('finalizing', 'finalized') THEN updated_at
                        ELSE :effective_now
                    END
                WHERE id = :session_id
                """
            ),
            params,
        )
        db.execute(
            text(
                """
                INSERT INTO finalize_jobs (
                    auction_id,
                    status,
                    retry_count,
                    last_error,
                    created_at,
                    updated_at
                )
                VALUES (
                    :session_id,
                    'pending',
                    0,
                    NULL,
                    :effective_now,
                    :effective_now
                )
                ON CONFLICT(auction_id) DO UPDATE SET
                    status = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN 'pending'
                        ELSE finalize_jobs.status
                    END,
                    last_error = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN NULL
                        ELSE finalize_jobs.last_error
                    END,
                    updated_at = CASE
                        WHEN finalize_jobs.status IN ('done', 'failed') THEN excluded.updated_at
                        ELSE finalize_jobs.updated_at
                    END
                """
            ),
            params,
        )
        return

    if db.scalar(select(FinalizeJob.id).where(FinalizeJob.auction_id == session_id)) is None:
        db.add(
            FinalizeJob(
                auction_id=int(session_id),
                status="pending",
                retry_count=0,
                last_error=None,
                created_at=effective_now,
                updated_at=effective_now,
            )
        )
    db.execute(
        update(AuctionSession)
        .where(AuctionSession.id == session_id)
        .values(
            status="finalizing",
            closed_by_user_id=current_user_id,
            actual_end_at=effective_now,
            updated_at=effective_now,
        )
    )


def _finalize_auction_async_request(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    context = _load_finalize_enqueue_context(
        db,
        session_id=session_id,
        current_user=current_user,
    )
    effective_now = utcnow()
    if context.session.status not in {"open", "closed", "finalizing", "finalized"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized")
    if not _can_enqueue_finalize_request_from_context(
        session=context.session,
        has_valid_bid=context.has_valid_bid,
        current_time=effective_now,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized yet")

    _persist_finalize_request_fast(
        db,
        session_id=context.session.id,
        current_user_id=current_user.user.id,
        effective_now=effective_now,
    )
    if context.session.status not in {"finalizing", "finalized"}:
        context.session.status = "finalizing"
        context.session.updated_at = effective_now
    if context.session.closed_by_user_id is None:
        context.session.closed_by_user_id = current_user.user.id
    if context.session.actual_end_at is None:
        context.session.actual_end_at = effective_now
    db.commit()
    _dispatch_finalize_post_processing_task_nonblocking(context.session.id)
    return _build_enqueued_finalize_response(
        db,
        session=context.session,
        group=context.group,
        current_user=current_user,
    )


def _finalize_auction_fast(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    started_at = perf_counter()

    logger.info(
        "Auction finalization started",
        extra={
            "event": "auction.finalize.started",
            "auction_session_id": session_id,
        },
    )

    try:
        if not _finalize_task_executes_inline():
            return _finalize_auction_async_request(db, session_id, current_user)

        session, group = _get_owner_session(db, session_id, current_user)
        effective_now = utcnow()

        if session.status not in {"open", "closed", "finalizing", "finalized"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized")

        if not _can_enqueue_finalize_request(db, session=session, current_time=effective_now):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized yet")

        if session.status not in {"finalizing", "finalized"}:
            session.status = "finalizing"
        if session.closed_by_user_id is None:
            session.closed_by_user_id = current_user.user.id
        if session.actual_end_at is None:
            session.actual_end_at = effective_now
        session.updated_at = effective_now
        ensure_finalize_job_enqueued(db, session.id)

        db.commit()
        _dispatch_finalize_post_processing_task_nonblocking(session.id)
        if _finalize_task_executes_inline():
            db.expire_all()
            return _build_inline_finalization_response(
                db,
                session_id=session.id,
                current_user=current_user,
            )
        return _build_enqueued_finalize_response(
            db,
            session=session,
            group=group,
            current_user=current_user,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Auction finalization failed",
            extra={
                "event": "auction.finalize.failed",
                "auction_session_id": session_id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    finally:
        logger.info(
            "Auction finalization completed",
            extra={
                "event": "auction.finalize.completed",
                "auction_session_id": session_id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )


def finalize_auction(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    started_at = perf_counter()
    logger.info(
        "FINALIZE START",
        extra={
            "event": "auction.finalize.entry",
            "session_id": session_id,
        },
    )
    try:
        result = _finalize_auction_fast(db, session_id, current_user)
        _log_finalize_trace(
            "FINALIZE DONE",
            session_id=session_id,
            duration_ms=(perf_counter() - started_at) * 1000,
        )
        return result
    except IntegrityError:
        logger.exception(
            "FINALIZE FAILED",
            extra={
                "event": "auction.finalize.entry_failed",
                "session_id": session_id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "failure_type": "IntegrityError",
            },
        )
        db.rollback()
        recovered_response = _recover_finalize_request_after_conflict(
            db,
            session_id=session_id,
            current_user=current_user,
        )
        if recovered_response is not None:
            return recovered_response
        raise
    except Exception:
        logger.exception(
            "FINALIZE FAILED",
            extra={
                "event": "auction.finalize.entry_failed",
                "session_id": session_id,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise


def finalize_expired_open_auction_sessions(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict]:
    expired_sessions = list_expired_open_auction_sessions(db, now=now, limit=limit)
    finalized_sessions: list[dict] = []
    for session in expired_sessions:
        group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
        if group is None:
            continue
        owner = db.scalar(select(Owner).where(Owner.id == group.owner_id))
        finalized_by_user_id = session.opened_by_user_id or (owner.user_id if owner is not None else None)
        if finalized_by_user_id is None:
            continue
        total_bid_count = db.scalar(
            select(func.count(AuctionBid.id)).where(AuctionBid.auction_session_id == session.id)
        ) or 0
        valid_bid_count = _get_valid_bid_count(db, session.id)
        if total_bid_count > 0 and valid_bid_count == 0:
            continue
        if not can_finalize_auction_session(db, session, now=now):
            continue
        finalized_response = _finalize_loaded_auction_session(
            db,
            session=session,
            group=group,
            finalized_by_user_id=finalized_by_user_id,
            actor_user_id=finalized_by_user_id,
            publish_events=False,
            now_override=now,
        )
        finalized_sessions.append(finalized_response)
    return finalized_sessions


def get_owner_auction_console(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    session, group = _get_owner_session(db, session_id, current_user)
    bid_controls = resolve_session_bid_controls(session=session, group=group)

    total_bid_count = db.scalar(
        select(func.count(AuctionBid.id)).where(AuctionBid.auction_session_id == session.id)
    ) or 0
    valid_bid_count = _get_valid_bid_count(db, session.id)
    winning_bid = select_winning_bid(db, session.id)
    result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    now = utcnow()

    highest_bid_membership = None
    highest_bidder_name = None
    if winning_bid is not None:
        highest_bid_membership = db.scalar(
            select(GroupMembership).where(GroupMembership.id == winning_bid.membership_id)
        )
        if highest_bid_membership is not None:
            bidder = db.scalar(
                select(Subscriber).where(Subscriber.id == highest_bid_membership.subscriber_id)
            )
            if bidder is not None:
                highest_bidder_name = bidder.full_name

    winner_details = _get_membership_display_details(
        db,
        result.winner_membership_id if result is not None else None,
    )

    return {
        "sessionId": session.id,
        "groupTitle": group.title,
        "groupCode": group.group_code,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "minBidValue": bid_controls["minBidValue"],
        "maxBidValue": bid_controls["maxBidValue"],
        "minIncrement": bid_controls["minIncrement"],
        "auctionState": get_auction_state(session, now=now, has_result=result is not None),
        "cycleNo": session.cycle_no,
        "status": session.status,
        "scheduledStartAt": session.scheduled_start_at,
        "actualStartAt": session.actual_start_at,
        "actualEndAt": session.actual_end_at,
        "startTime": session.start_time,
        "endTime": session.end_time,
        "serverTime": now,
        "totalBidCount": int(total_bid_count),
        "validBidCount": int(valid_bid_count),
        "highestBidAmount": (
            money_int(winning_bid.bid_amount)
            if winning_bid and (not is_blind_auction(session) or result is not None)
            else None
        ),
        "highestBidMembershipNo": (
            highest_bid_membership.member_no
            if highest_bid_membership and (not is_blind_auction(session) or result is not None)
            else None
        ),
        "highestBidderName": (
            highest_bidder_name
            if highest_bidder_name and (not is_blind_auction(session) or result is not None)
            else None
        ),
        "canFinalize": can_finalize_auction_session(db, session, now=now),
        "auctionResultId": result.id if result else None,
        "finalizedAt": result.finalized_at if result else session.updated_at if session.status == "finalized" else None,
        "finalizedByName": _get_user_display_name(db, result.finalized_by_user_id if result is not None else None),
        "winnerMembershipId": winner_details["winnerMembershipId"],
        "winnerMembershipNo": winner_details["winnerMembershipNo"],
        "winnerName": winner_details["winnerName"],
        "winningBidId": result.winning_bid_id if result else session.winning_bid_id,
        "winningBidAmount": money_int(result.winning_bid_amount) if result else None,
        "ownerCommissionAmount": money_int(result.owner_commission_amount) if result else None,
        "dividendPoolAmount": money_int(result.dividend_pool_amount) if result else None,
        "dividendPerMemberAmount": money_int(result.dividend_per_member_amount) if result else None,
        "winnerPayoutAmount": money_int(result.winner_payout_amount) if result else None,
        "finalizationMessage": _get_no_bid_finalization_message(
            session=session,
            result=result,
            valid_bid_count=valid_bid_count,
        ),
    }
