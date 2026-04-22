from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.money import money_int
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.core.time import utcnow
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Owner, Subscriber
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
from app.modules.payments.auction_payout_engine import calculate_payout
from app.modules.payments.payout_service import ensure_auction_payout


DEFAULT_MIN_BID_VALUE = 0
DEFAULT_MIN_INCREMENT = 1


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


def _get_no_bid_finalization_message(
    *,
    session: AuctionSession,
    result: AuctionResult | None,
    valid_bid_count: int,
) -> str | None:
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
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
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
    publish_auction_bid_event(
        session.id,
        {
            "room": room_snapshot,
            "bidId": bid.id,
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
    winning_bid: AuctionBid,
    winner_membership_id: int,
    finalized_by_user_id: int,
    finalized_at: datetime | None = None,
    dividend_pool_amount: int,
    dividend_per_member_amount: int,
    owner_commission_amount: int,
    winner_payout_amount: int,
) -> AuctionResult:
    if winning_bid.auction_session_id != session.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Winning bid does not belong to this session")

    winner_membership = db.scalar(
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

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")
    if should_advance_group:
        _advance_group_cycle(group, session)

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
    ensure_auction_payout(db, result=result)
    db.commit()
    dispatch_staged_notifications(db)
    db.refresh(result)
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


def create_auction_result(db: Session, *, session_id: int, finalized_by_user_id: int) -> AuctionResult | None:
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chit group not found")

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
        winning_bid=winning_bid,
        winner_membership_id=winner_membership_id,
        finalized_by_user_id=finalized_by_user_id,
        finalized_at=utcnow(),
        dividend_pool_amount=money_int(payout_calculation.dividend_pool_amount),
        dividend_per_member_amount=money_int(payout_calculation.dividend_per_member_amount),
        owner_commission_amount=money_int(payout_calculation.owner_commission_amount),
        winner_payout_amount=money_int(payout_calculation.winner_payout_amount),
    )


def _finalize_loaded_auction_session(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    finalized_by_user_id: int,
    current_user: CurrentUser | None = None,
    actor_user_id: int | None = None,
    publish_events: bool = True,
    now_override: datetime | None = None,
) -> dict:
    effective_now = now_override or utcnow()
    existing_result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    audit_before = _serialize_auction_audit_state(session, existing_result)
    valid_bid_count = _get_valid_bid_count(db, session.id)
    no_bid_already_finalized = (
        session.status == "finalized"
        and existing_result is None
        and valid_bid_count == 0
    )

    if session.status not in {"open", "closed", "finalized"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized")
    if existing_result is None and not no_bid_already_finalized and not can_finalize_auction_session(db, session, now=effective_now):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session cannot be finalized yet")

    if no_bid_already_finalized:
        console_snapshot = None
        if current_user is not None and current_user.owner is not None:
            console_snapshot = get_owner_auction_console(db, session.id, current_user)
        return {
            "sessionId": session.id,
            "groupId": group.id,
            "auctionMode": get_auction_mode(session),
            "commissionMode": (session.commission_mode or "NONE").upper(),
            "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
            "cycleNo": session.cycle_no,
            "status": session.status,
            "closedAt": session.actual_end_at,
            "finalizedAt": session.updated_at,
            "closedByUserId": session.closed_by_user_id,
            "finalizedByUserId": finalized_by_user_id,
            "finalizedByName": _get_user_display_name(db, finalized_by_user_id),
            "finalizationMessage": _get_no_bid_finalization_message(
                session=session,
                result=None,
                valid_bid_count=valid_bid_count,
            ),
            "resultSummary": _build_result_summary(db, session, None),
            "console": console_snapshot,
        }

    if session.status == "open":
        session.status = "closed"
        session.actual_end_at = effective_now
        session.closed_by_user_id = finalized_by_user_id
        session.updated_at = effective_now
        db.commit()
        db.refresh(session)

    result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    if result is None:
        result = create_auction_result(db, session_id=session.id, finalized_by_user_id=finalized_by_user_id)
        session = db.scalar(select(AuctionSession).where(AuctionSession.id == session.id))
    elif existing_result is not None:
        ensure_auction_payout(db, result=result)

    session.status = "finalized"
    session.updated_at = effective_now
    if session.closed_by_user_id is None:
        session.closed_by_user_id = finalized_by_user_id
    if session.actual_end_at is None:
        session.actual_end_at = effective_now
    valid_bid_count = _get_valid_bid_count(db, session.id)
    finalization_message = _get_no_bid_finalization_message(
        session=session,
        result=result,
        valid_bid_count=valid_bid_count,
    )
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
    if result is not None:
        notify_auction_finalized(db, session=session, result=result)
    db.commit()
    dispatch_staged_notifications(db)
    db.refresh(session)
    console_snapshot = None
    if current_user is not None and current_user.owner is not None:
        console_snapshot = get_owner_auction_console(db, session.id, current_user)
    if publish_events and console_snapshot is not None:
        publish_auction_finalize_event(
            session.id,
            {
                "console": console_snapshot,
            },
        )

    return {
        "sessionId": session.id,
        "groupId": group.id,
        "auctionMode": get_auction_mode(session),
        "commissionMode": (session.commission_mode or "NONE").upper(),
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "cycleNo": session.cycle_no,
        "status": session.status,
        "closedAt": session.actual_end_at,
        "finalizedAt": result.finalized_at if result else session.updated_at,
        "closedByUserId": session.closed_by_user_id,
        "finalizedByUserId": finalized_by_user_id,
        "finalizedByName": _get_user_display_name(
            db,
            result.finalized_by_user_id if result is not None else finalized_by_user_id,
        ),
        "finalizationMessage": finalization_message,
        "resultSummary": _build_result_summary(db, session, result),
        "console": console_snapshot,
    }


def _advance_group_cycle(group: ChitGroup, session: AuctionSession) -> None:
    is_terminal_cycle = session.cycle_no >= group.cycle_count
    group.current_cycle_no = min(session.cycle_no + 1, group.cycle_count)
    group.bidding_enabled = not is_terminal_cycle
    group.status = "completed" if is_terminal_cycle else "active"
    group.updated_at = utcnow()


def _get_owner_session(db: Session, session_id: int, current_user: CurrentUser) -> tuple[AuctionSession, ChitGroup]:
    owner = require_owner(current_user)
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction group not found")
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


def finalize_auction(db: Session, session_id: int, current_user: CurrentUser) -> dict:
    session, group = _get_owner_session(db, session_id, current_user)
    return _finalize_loaded_auction_session(
        db,
        session=session,
        group=group,
        finalized_by_user_id=current_user.user.id,
        current_user=current_user,
        actor_user_id=current_user.user.id,
    )


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
        finalized_sessions.append(
            _finalize_loaded_auction_session(
                db,
                session=session,
                group=group,
                finalized_by_user_id=finalized_by_user_id,
                actor_user_id=finalized_by_user_id,
                publish_events=False,
                now_override=now,
            )
        )
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
