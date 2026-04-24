from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.security import CurrentUser, require_subscriber
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.modules.groups.service import (
    _determine_first_payable_cycle_no,
    _create_membership_installments,
    _serialize_membership,
)
from app.modules.groups.slot_service import create_membership_slots, sync_membership_slot_state


def _payload_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _membership_count(db: Session, group_id: int) -> int:
    slot_count = db.scalar(
        select(func.count(MembershipSlot.id)).where(MembershipSlot.group_id == group_id)
    )
    if slot_count:
        return int(slot_count)

    membership_count = db.scalar(
        select(func.count()).select_from(GroupMembership).where(GroupMembership.group_id == group_id)
    )
    return int(membership_count or 0)


def join_group(db: Session, group_id: int, payload, current_user: CurrentUser):
    subscriber = require_subscriber(current_user)
    subscriber_id = _payload_value(payload, "subscriberId")
    member_no = int(_payload_value(payload, "memberNo"))
    requested_slot_count = int(_payload_value(payload, "slotCount", 1) or 1)

    if subscriber.id != subscriber_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot join for another subscriber")
    if requested_slot_count < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Slot count must be at least 1",
        )

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is not active")
    if (group.visibility or "private") != "public":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private groups require owner approval or invite",
        )
    existing_membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    if existing_membership is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")
    existing_group_slot = db.scalar(
        select(MembershipSlot.user_id).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.slot_number == member_no,
        )
    )
    if existing_group_slot is not None and int(existing_group_slot) != int(subscriber.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member number is already taken")
    if existing_group_slot is None:
        existing_member_no = db.scalar(
            select(GroupMembership.id).where(
                GroupMembership.group_id == group.id,
                GroupMembership.member_no == member_no,
            )
        )
        if existing_member_no is not None and existing_membership is not None and int(existing_member_no) == int(existing_membership.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Member number is already assigned to this subscriber",
            )
        if existing_member_no is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member number is already taken")
    elif existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Member number is already assigned to this subscriber",
        )

    if _membership_count(db, group.id) + requested_slot_count > group.member_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full")
    if member_no < 1 or member_no > group.member_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Member number must be between 1 and {group.member_count}",
        )

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    created_membership = True
    db.add(membership)
    db.flush()

    created_slots = create_membership_slots(
        db,
        membership,
        slot_count=requested_slot_count,
        preferred_slot_numbers=[member_no],
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

    log_audit_event(
        db,
        action="group.membership.joined" if created_membership else "group.membership.slots_joined",
        entity_type="group_membership",
        entity_id=membership.id,
        current_user=current_user,
        owner_id=group.owner_id,
        metadata=(
            {
                "groupId": group.id,
                "memberNo": member_no,
                "subscriberId": subscriber.id,
            }
            if created_membership
            else {
                "groupId": group.id,
                "memberNo": member_no,
                "subscriberId": subscriber.id,
                "requestedSlotCount": requested_slot_count,
                "createdSlotNumbers": [slot.slot_number for slot in created_slots],
            }
        ),
        after={
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
            "installmentCount": group.cycle_count,
        },
    )

    db.commit()
    db.refresh(membership)
    slot_summary = sync_membership_slot_state(db, membership)
    return _serialize_membership(membership, slot_summary=slot_summary)
