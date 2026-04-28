from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.core.time import utcnow
from app.models.chit import ChitGroup, GroupJoinRequest, GroupMembership, Installment, MembershipSlot
from app.models.user import Subscriber
from app.modules.groups.service import (
    _create_membership_installments,
    _determine_first_payable_cycle_no,
    _serialize_membership,
)
from app.modules.groups.slot_service import (
    create_membership_slots,
    ensure_membership_slot,
    get_group_capacity_summary,
    get_next_member_no,
    sync_membership_slot_state,
)


def _calculate_payment_score(db: Session, *, subscriber_id: int) -> int | None:
    due_installments = db.scalar(
        select(func.count(Installment.id))
        .join(GroupMembership, GroupMembership.id == Installment.membership_id)
        .where(
            GroupMembership.subscriber_id == subscriber_id,
            Installment.due_date <= date.today(),
        )
    ) or 0
    if int(due_installments) <= 0:
        return None
    paid_installments = db.scalar(
        select(func.count(Installment.id))
        .join(GroupMembership, GroupMembership.id == Installment.membership_id)
        .where(
            GroupMembership.subscriber_id == subscriber_id,
            Installment.due_date <= date.today(),
            ((Installment.status == "paid") | (Installment.balance_amount <= 0)),
        )
    ) or 0
    return int(round((int(paid_installments) / int(due_installments)) * 100))


def _serialize_join_request(join_request: GroupJoinRequest, *, subscriber: Subscriber | None = None, payment_score: int | None = None) -> dict:
    return {
        "id": join_request.id,
        "groupId": join_request.group_id,
        "subscriberId": join_request.subscriber_id,
        "subscriberName": subscriber.full_name if subscriber is not None else None,
        "requestedSlotCount": join_request.requested_slot_count,
        "paymentScore": payment_score,
        "status": join_request.status,
        "createdAt": join_request.created_at,
        "reviewedAt": join_request.reviewed_at,
        "approvedMembershipId": join_request.approved_membership_id,
    }


def _supports_row_locking(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name != "sqlite"


def _apply_for_update(db: Session, statement):
    if _supports_row_locking(db):
        return statement.with_for_update()
    return statement


def _get_group_or_404(db: Session, group_id: int, *, for_update: bool = False) -> ChitGroup:
    statement = select(ChitGroup).where(ChitGroup.id == group_id)
    if for_update:
        statement = _apply_for_update(db, statement)
    group = db.scalar(statement)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


def _get_subscriber_or_404(db: Session, subscriber_id: int) -> Subscriber:
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == subscriber_id))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    return subscriber


def create_join_request(db: Session, group_id: int, payload, current_user: CurrentUser) -> dict:
    subscriber = require_subscriber(current_user)
    group = _get_group_or_404(db, group_id)
    requested_slot_count = int(getattr(payload, "slotCount", 1) or 1)

    if requested_slot_count < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Slot count must be at least 1")
    if group.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is not active")
    if (group.visibility or "private") != "public":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Join requests are only supported for public groups")

    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    if membership is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")

    existing_pending = db.scalar(
        select(GroupJoinRequest).where(
            GroupJoinRequest.group_id == group.id,
            GroupJoinRequest.subscriber_id == subscriber.id,
            GroupJoinRequest.status == "pending",
        )
    )
    if existing_pending is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Join request is already pending")

    join_request = GroupJoinRequest(
        group_id=group.id,
        subscriber_id=subscriber.id,
        requested_slot_count=requested_slot_count,
        status="pending",
    )
    db.add(join_request)
    db.flush()
    log_audit_event(
        db,
        action="group.join_request.created",
        entity_type="group_join_request",
        entity_id=join_request.id,
        current_user=current_user,
        owner_id=group.owner_id,
        metadata={"groupId": group.id, "subscriberId": subscriber.id},
        after=_serialize_join_request(
            join_request,
            subscriber=subscriber,
            payment_score=_calculate_payment_score(db, subscriber_id=subscriber.id),
        ),
    )
    db.commit()
    db.refresh(join_request)
    return _serialize_join_request(
        join_request,
        subscriber=subscriber,
        payment_score=_calculate_payment_score(db, subscriber_id=subscriber.id),
    )


def list_join_requests(db: Session, group_id: int, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    join_requests = db.scalars(
        select(GroupJoinRequest)
        .where(
            GroupJoinRequest.group_id == group.id,
            GroupJoinRequest.status == "pending",
        )
        .order_by(GroupJoinRequest.created_at.desc(), GroupJoinRequest.id.desc())
    ).all()
    subscribers = {
        subscriber.id: subscriber
        for subscriber in db.scalars(
            select(Subscriber).where(Subscriber.id.in_([join_request.subscriber_id for join_request in join_requests]))
        ).all()
    } if join_requests else {}
    return [
        _serialize_join_request(
            join_request,
            subscriber=subscribers.get(join_request.subscriber_id),
            payment_score=_calculate_payment_score(db, subscriber_id=join_request.subscriber_id),
        )
        for join_request in join_requests
    ]


def approve_join_request(db: Session, group_id: int, join_request_id: int, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id, for_update=True)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    join_request = db.scalar(
        _apply_for_update(
            db,
            select(GroupJoinRequest).where(
                GroupJoinRequest.id == join_request_id,
                GroupJoinRequest.group_id == group.id,
            ),
        )
    )
    if join_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    if join_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Join request is not pending")

    subscriber = _get_subscriber_or_404(db, join_request.subscriber_id)
    existing_membership = db.scalar(
        _apply_for_update(
            db,
            select(GroupMembership).where(
                GroupMembership.group_id == group.id,
                GroupMembership.subscriber_id == subscriber.id,
            ),
        )
    )
    if existing_membership is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")

    capacity_summary = get_group_capacity_summary(db, group=group)
    if capacity_summary.occupied_slots + int(join_request.requested_slot_count) > int(group.member_count):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full")

    try:
        next_member_no = get_next_member_no(db, group=group)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full") from exc

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=next_member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db.add(membership)
    db.flush()

    created_slots = create_membership_slots(
        db,
        membership,
        slot_count=int(join_request.requested_slot_count),
        preferred_slot_numbers=[membership.member_no],
    )
    if not created_slots:
        ensure_membership_slot(db, membership)
    slot_summary = sync_membership_slot_state(db, membership)
    first_payable_cycle_no = _determine_first_payable_cycle_no(group)
    _create_membership_installments(
        db,
        group=group,
        membership=membership,
        slot_count=slot_summary.total_slots,
        first_payable_cycle_no=first_payable_cycle_no,
    )

    join_request.status = "approved"
    join_request.approved_membership_id = membership.id
    join_request.reviewed_by_user_id = current_user.user.id
    join_request.reviewed_at = utcnow()
    join_request.updated_at = utcnow()
    log_audit_event(
        db,
        action="group.join_request.approved",
        entity_type="group_join_request",
        entity_id=join_request.id,
        current_user=current_user,
        owner_id=group.owner_id,
        metadata={"groupId": group.id, "subscriberId": subscriber.id},
        after=_serialize_join_request(
            join_request,
            subscriber=subscriber,
            payment_score=_calculate_payment_score(db, subscriber_id=subscriber.id),
        ),
    )
    db.commit()
    db.refresh(membership)
    slot_summary = sync_membership_slot_state(db, membership)
    return _serialize_membership(membership, slot_summary=slot_summary)


def reject_join_request(db: Session, group_id: int, join_request_id: int, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    join_request = db.scalar(
        select(GroupJoinRequest).where(
            GroupJoinRequest.id == join_request_id,
            GroupJoinRequest.group_id == group.id,
        )
    )
    if join_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    if join_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Join request is not pending")

    subscriber = _get_subscriber_or_404(db, join_request.subscriber_id)
    join_request.status = "rejected"
    join_request.reviewed_by_user_id = current_user.user.id
    join_request.reviewed_at = utcnow()
    join_request.updated_at = utcnow()
    payload = _serialize_join_request(
        join_request,
        subscriber=subscriber,
        payment_score=_calculate_payment_score(db, subscriber_id=subscriber.id),
    )
    log_audit_event(
        db,
        action="group.join_request.rejected",
        entity_type="group_join_request",
        entity_id=join_request.id,
        current_user=current_user,
        owner_id=group.owner_id,
        metadata={"groupId": group.id, "subscriberId": subscriber.id},
        after=payload,
    )
    db.commit()
    return payload
