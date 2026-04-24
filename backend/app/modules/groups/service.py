from decimal import Decimal, InvalidOperation
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.money import money_int
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner
from app.core.time import utcnow
from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.modules.auctions.service import validate_session_bid_controls
from app.modules.auctions.commission_service import validate_commission_config
from app.modules.groups.membership_validation import validate_membership_creation
from app.modules.groups.slot_service import create_membership_slots, ensure_membership_slot, sync_membership_slot_state


def validate_group_penalty_config(
    *,
    penalty_enabled: bool | None,
    penalty_type: str | None,
    penalty_value: float | int | Decimal | None,
    grace_period_days: int | None,
) -> dict[str, object]:
    normalized_enabled = bool(penalty_enabled)
    normalized_grace_days = int(grace_period_days or 0)
    if normalized_grace_days < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grace period days must be zero or more",
        )

    if not normalized_enabled:
        return {
            "penaltyEnabled": False,
            "penaltyType": None,
            "penaltyValue": None,
            "gracePeriodDays": normalized_grace_days,
        }

    normalized_penalty_type = (penalty_type or "").strip().upper()
    if normalized_penalty_type not in {"FIXED", "PERCENTAGE"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Penalty type must be FIXED or PERCENTAGE when penalties are enabled",
        )

    if penalty_value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Penalty value must be provided when penalties are enabled",
        )

    if normalized_penalty_type == "PERCENTAGE":
        try:
            normalized_penalty_value = Decimal(str(penalty_value))
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Percentage penalty value must be numeric",
            ) from exc
        if normalized_penalty_value < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Percentage penalty value must be zero or more",
            )
        if normalized_penalty_value > Decimal("100"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Percentage penalty value must not exceed 100",
            )
    else:
        normalized_penalty_value = int(penalty_value)
        if normalized_penalty_value < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Fixed penalty value must be zero or more",
            )

    return {
        "penaltyEnabled": True,
        "penaltyType": normalized_penalty_type,
        "penaltyValue": normalized_penalty_value,
        "gracePeriodDays": normalized_grace_days,
    }


def serialize_penalty_value(penalty_type: str | None, penalty_value) -> float | int | None:
    if penalty_value is None:
        return None
    if (penalty_type or "").strip().upper() == "PERCENTAGE":
        return float(penalty_value)
    return money_int(penalty_value)


def _normalize_group_visibility(value: str | None) -> str:
    normalized = (value or "private").strip().lower()
    if normalized not in {"public", "private"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Visibility must be public or private",
        )
    return normalized


def serialize_group(group: ChitGroup) -> dict:
    return {
        "id": group.id,
        "ownerId": group.owner_id,
        "groupCode": group.group_code,
        "title": group.title,
        "chitValue": money_int(group.chit_value),
        "installmentAmount": money_int(group.installment_amount),
        "memberCount": group.member_count,
        "cycleCount": group.cycle_count,
        "cycleFrequency": group.cycle_frequency,
        "visibility": group.visibility,
        "startDate": group.start_date,
        "firstAuctionDate": group.first_auction_date,
        "penaltyEnabled": group.penalty_enabled,
        "penaltyType": group.penalty_type,
        "penaltyValue": serialize_penalty_value(group.penalty_type, group.penalty_value),
        "gracePeriodDays": group.grace_period_days,
        "currentCycleNo": group.current_cycle_no,
        "biddingEnabled": group.bidding_enabled,
        "status": group.status,
    }


def create_group(db: Session, payload, current_user: CurrentUser):
    owner = require_owner(current_user)
    if payload.ownerId is not None and payload.ownerId != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create groups for another owner")
    penalty_config = validate_group_penalty_config(
        penalty_enabled=getattr(payload, "penaltyEnabled", False),
        penalty_type=getattr(payload, "penaltyType", None),
        penalty_value=getattr(payload, "penaltyValue", None),
        grace_period_days=getattr(payload, "gracePeriodDays", 0),
    )
    visibility = _normalize_group_visibility(getattr(payload, "visibility", "private"))

    group = ChitGroup(
        owner_id=owner.id,
        group_code=payload.groupCode,
        title=payload.title,
        chit_value=payload.chitValue,
        installment_amount=payload.installmentAmount,
        member_count=payload.memberCount,
        cycle_count=payload.cycleCount,
        cycle_frequency=payload.cycleFrequency,
        visibility=visibility,
        start_date=payload.startDate,
        first_auction_date=payload.firstAuctionDate,
        current_cycle_no=1,
        bidding_enabled=True,
        penalty_enabled=penalty_config["penaltyEnabled"],
        penalty_type=penalty_config["penaltyType"],
        penalty_value=penalty_config["penaltyValue"],
        grace_period_days=penalty_config["gracePeriodDays"],
        status="active" if visibility == "public" else "draft",
    )
    db.add(group)
    db.flush()
    log_audit_event(
        db,
        action="group.created",
        entity_type="chit_group",
        entity_id=group.id,
        current_user=current_user,
        metadata={
            "groupCode": group.group_code,
            "title": group.title,
            "status": group.status,
        },
        after={
            "groupId": group.id,
            "groupCode": group.group_code,
            "title": group.title,
            "installmentAmount": money_int(group.installment_amount),
            "memberCount": group.member_count,
            "cycleCount": group.cycle_count,
            "visibility": group.visibility,
            "status": group.status,
            "penaltyEnabled": group.penalty_enabled,
            "penaltyType": group.penalty_type,
            "penaltyValue": serialize_penalty_value(group.penalty_type, group.penalty_value),
            "gracePeriodDays": group.grace_period_days,
        },
    )
    db.commit()
    db.refresh(group)
    return serialize_group(group)


def list_groups(
    db: Session,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)
    statement = select(ChitGroup).where(ChitGroup.owner_id == owner.id).order_by(ChitGroup.id.asc())
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        groups = db.scalars(statement).all()
    else:
        total_count = count_statement(db, statement)
        groups = db.scalars(apply_pagination(statement, pagination)).all()

    return [serialize_group(group) for group in groups] if pagination is None else build_paginated_response(
        [serialize_group(group) for group in groups],
        pagination,
        total_count,
    )


def _add_months(base_date: date, months_to_add: int) -> date:
    month_index = base_date.month - 1 + months_to_add
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _calculate_due_date(start_date: date, cycle_frequency: str, cycle_no: int) -> date:
    if cycle_frequency == "weekly":
        return start_date + timedelta(days=(cycle_no - 1) * 7)
    return _add_months(start_date, cycle_no - 1)


def _normalize_auction_mode(value: str | None) -> str:
    normalized = (value or "LIVE").strip().upper()
    if normalized not in {"LIVE", "BLIND", "FIXED"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid auction mode")
    return normalized


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _membership_cycle_due_amount(group: ChitGroup, *, slot_count: int) -> int:
    return money_int(group.installment_amount) * int(slot_count)


def _determine_first_payable_cycle_no(group: ChitGroup, *, as_of_date: date | None = None) -> int:
    effective_as_of_date = as_of_date or utcnow().date()
    first_cycle_no = max(int(group.current_cycle_no or 1), 1)
    if first_cycle_no > int(group.cycle_count or 0):
        return first_cycle_no

    current_cycle_due_date = _calculate_due_date(group.start_date, group.cycle_frequency, first_cycle_no)
    if current_cycle_due_date <= effective_as_of_date:
        return min(first_cycle_no + 1, int(group.cycle_count or 0) + 1)
    return first_cycle_no


def _sync_membership_installments_for_slot_count(
    db: Session,
    *,
    group: ChitGroup,
    membership: GroupMembership,
    slot_count: int,
) -> None:
    due_amount = _membership_cycle_due_amount(group, slot_count=slot_count)
    installments = db.scalars(
        select(Installment)
        .where(Installment.membership_id == membership.id)
        .order_by(Installment.cycle_no.asc(), Installment.id.asc())
    ).all()
    if not installments:
        _create_membership_installments(
            db,
            group=group,
            membership=membership,
            slot_count=slot_count,
        )
        return
    for installment in installments:
        paid_amount = money_int(installment.paid_amount or 0)
        balance_amount = max(due_amount - paid_amount, 0)
        installment.due_amount = due_amount
        installment.balance_amount = balance_amount
        if balance_amount <= 0:
            installment.status = "paid"
        elif paid_amount > 0:
            installment.status = "partial"
        else:
            installment.status = "pending"


def _create_membership_installments(
    db: Session,
    *,
    group: ChitGroup,
    membership: GroupMembership,
    slot_count: int,
    first_payable_cycle_no: int | None = None,
) -> None:
    due_amount = _membership_cycle_due_amount(group, slot_count=slot_count)
    starting_cycle_no = max(int(first_payable_cycle_no or 1), 1)
    for cycle_no in range(starting_cycle_no, group.cycle_count + 1):
        due_date = _calculate_due_date(group.start_date, group.cycle_frequency, cycle_no)
        installment = Installment(
            group_id=group.id,
            membership_id=membership.id,
            cycle_no=cycle_no,
            due_date=due_date,
            due_amount=due_amount,
            penalty_amount=0,
            paid_amount=0,
            balance_amount=due_amount,
            status="pending",
        )
        db.add(installment)


def _serialize_membership(membership: GroupMembership, *, slot_summary) -> dict:
    return {
        "id": membership.id,
        "groupId": membership.group_id,
        "subscriberId": membership.subscriber_id,
        "memberNo": membership.member_no,
        "slotCount": slot_summary.total_slots,
        "membershipStatus": membership.membership_status,
        "prizedStatus": membership.prized_status,
        "canBid": membership.can_bid,
        "wonSlotCount": slot_summary.won_slots,
        "remainingSlotCount": slot_summary.available_slots,
    }


def create_membership(db: Session, group_id: int, payload, current_user: CurrentUser):
    context = validate_membership_creation(db, group_id, payload, current_user)
    group = context.group
    subscriber = context.subscriber
    membership = context.existing_membership
    created_membership = membership is None

    if membership is None:
        membership = GroupMembership(
            group_id=group.id,
            subscriber_id=subscriber.id,
            member_no=payload.memberNo,
            membership_status="active",
            prized_status="unprized",
            can_bid=True,
        )
        db.add(membership)
        db.flush()
    else:
        ensure_membership_slot(db, membership)

    created_slots = create_membership_slots(
        db,
        membership,
        slot_count=context.requested_slot_count,
        preferred_slot_numbers=[payload.memberNo],
    )
    if not created_slots:
        ensure_membership_slot(db, membership)
    slot_summary = sync_membership_slot_state(db, membership)
    if created_membership:
        first_payable_cycle_no = _determine_first_payable_cycle_no(group)
        _create_membership_installments(
            db,
            group=group,
            membership=membership,
            slot_count=slot_summary.total_slots,
            first_payable_cycle_no=first_payable_cycle_no,
        )
    elif created_slots:
        _sync_membership_installments_for_slot_count(
            db,
            group=group,
            membership=membership,
            slot_count=slot_summary.total_slots,
        )

    audit_action = "group.membership.created" if created_membership else "group.membership.slots_added"
    audit_after = {
        "groupId": group.id,
        "membershipId": membership.id,
        "subscriberId": subscriber.id,
        "memberNo": membership.member_no,
        "membershipStatus": membership.membership_status,
        "prizedStatus": membership.prized_status,
        "canBid": membership.can_bid,
        "slotCount": slot_summary.total_slots,
        "wonSlotCount": slot_summary.won_slots,
        "remainingSlotCount": slot_summary.available_slots,
    }
    if created_membership:
        audit_after["installmentCount"] = group.cycle_count
    log_audit_event(
        db,
        action=audit_action,
        entity_type="group_membership",
        entity_id=membership.id,
        current_user=current_user,
        metadata={
            "groupId": group.id,
            "memberNo": payload.memberNo,
            "subscriberId": subscriber.id,
            "requestedSlotCount": context.requested_slot_count,
            "createdSlotNumbers": [slot.slot_number for slot in created_slots],
        },
        after=audit_after,
    )

    db.commit()
    db.refresh(membership)
    slot_summary = sync_membership_slot_state(db, membership)
    return _serialize_membership(membership, slot_summary=slot_summary)


def create_auction_session(db: Session, group_id: int, payload, current_user: CurrentUser):
    owner = require_owner(current_user)
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    scheduled_start = datetime.combine(
        group.first_auction_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    auction_mode = _normalize_auction_mode(getattr(payload, "auctionMode", None))
    commission_mode, commission_value = validate_commission_config(
        mode=getattr(payload, "commissionMode", None),
        value=getattr(payload, "commissionValue", None),
        group=group,
    )
    bid_controls = validate_session_bid_controls(
        group=group,
        min_bid_value=getattr(payload, "minBidValue", None),
        max_bid_value=getattr(payload, "maxBidValue", None),
        min_increment=getattr(payload, "minIncrement", None),
    )
    configured_start = _normalize_datetime(getattr(payload, "startTime", None))
    configured_end = _normalize_datetime(getattr(payload, "endTime", None))

    if auction_mode != "BLIND" and (configured_start is not None or configured_end is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="startTime and endTime are only supported for blind auctions",
        )

    if auction_mode == "BLIND":
        if (configured_start is None) != (configured_end is None):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Blind auctions require both startTime and endTime together",
            )
        start_time = configured_start or scheduled_start
        end_time = configured_end or (start_time + timedelta(seconds=payload.biddingWindowSeconds))
        if end_time <= start_time:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Blind auction endTime must be later than startTime",
            )
        actual_start = start_time
    else:
        start_time = None
        end_time = None
        # Keep the legacy "create and bid immediately" owner flow intact for live/fixed sessions.
        actual_start = utcnow()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=payload.cycleNo,
        scheduled_start_at=scheduled_start,
        actual_start_at=actual_start,
        start_time=start_time,
        end_time=end_time,
        auction_mode=auction_mode,
        commission_mode=commission_mode,
        commission_value=int(commission_value) if commission_value is not None else None,
        min_bid_value=bid_controls["minBidValue"],
        max_bid_value=bid_controls["maxBidValue"],
        min_increment=bid_controls["minIncrement"],
        bidding_window_seconds=payload.biddingWindowSeconds,
        status="open",
        opened_by_user_id=current_user.user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "groupId": session.group_id,
        "cycleNo": session.cycle_no,
        "auctionMode": session.auction_mode,
        "commissionMode": session.commission_mode,
        "commissionValue": money_int(session.commission_value) if session.commission_value is not None else None,
        "minBidValue": session.min_bid_value,
        "maxBidValue": session.max_bid_value,
        "minIncrement": session.min_increment,
        "status": session.status,
        "biddingWindowSeconds": session.bidding_window_seconds,
        "startTime": session.start_time,
        "endTime": session.end_time,
    }
