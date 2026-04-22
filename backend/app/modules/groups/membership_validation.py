from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_owner
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Subscriber


@dataclass(slots=True)
class ValidatedMembershipCreateContext:
    owner: object
    group: ChitGroup
    subscriber: Subscriber
    existing_membership: GroupMembership | None
    requested_slot_count: int


def _normalize_requested_slot_count(payload) -> int:
    requested_slot_count = int(getattr(payload, "slotCount", 1) or 1)
    if requested_slot_count < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Slot count must be at least 1",
        )
    return requested_slot_count


def _get_group_occupied_slot_count(db: Session, *, group_id: int) -> int:
    slot_count = db.scalar(
        select(func.count(MembershipSlot.id)).where(MembershipSlot.group_id == group_id)
    )
    if slot_count:
        return int(slot_count)

    membership_count = db.scalar(
        select(func.count(GroupMembership.id)).where(GroupMembership.group_id == group_id)
    )
    return int(membership_count or 0)


def validate_membership_creation(db: Session, group_id: int, payload, current_user: CurrentUser) -> ValidatedMembershipCreateContext:
    owner = require_owner(current_user)
    requested_slot_count = _normalize_requested_slot_count(payload)

    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    subscriber = db.scalar(
        select(Subscriber).where(
            Subscriber.id == payload.subscriberId,
            Subscriber.owner_id == owner.id,
        )
    )
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscriber does not belong to this owner")
    if subscriber.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscriber is not active")
    existing_membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    existing_group_slot = db.scalar(
        select(MembershipSlot.user_id).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.slot_number == payload.memberNo,
        )
    )
    if existing_group_slot is not None and int(existing_group_slot) != int(subscriber.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member number is already taken")
    if existing_group_slot is None:
        existing_member_no = db.scalar(
            select(GroupMembership.id).where(
                GroupMembership.group_id == group.id,
                GroupMembership.member_no == payload.memberNo,
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

    occupied_slot_count = _get_group_occupied_slot_count(db, group_id=group.id)
    if occupied_slot_count + requested_slot_count > group.member_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full")
    if payload.memberNo < 1 or payload.memberNo > group.member_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Member number must be between 1 and {group.member_count}",
        )

    return ValidatedMembershipCreateContext(
        owner=owner,
        group=group,
        subscriber=subscriber,
        existing_membership=existing_membership,
        requested_slot_count=requested_slot_count,
    )
