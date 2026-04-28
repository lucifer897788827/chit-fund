from sqlalchemy import func, select
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.chit import ChitGroup
from app.models.chit import GroupMembership
from app.models.user import Subscriber
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.modules.groups.invite_service import mark_group_invite_accepted, mark_group_invite_rejected, resolve_invite_status
from app.modules.groups.service import serialize_group
from app.modules.groups.service import (
    _create_membership_installments,
    _determine_first_payable_cycle_no,
    _serialize_membership,
)
from app.modules.groups.slot_service import create_membership_slots, ensure_membership_slot, sync_membership_slot_state


def _serialize_membership_request_record(membership: GroupMembership) -> dict:
    return {
        "membershipId": membership.id,
        "groupId": membership.group_id,
        "subscriberId": membership.subscriber_id,
        "memberNo": membership.member_no,
        "membershipStatus": membership.membership_status,
        "requestedAt": membership.joined_at,
    }


def list_public_chits(db: Session) -> list[dict]:
    groups = db.scalars(
        select(ChitGroup)
        .where(
            ChitGroup.visibility == "public",
            ChitGroup.status == "active",
        )
        .order_by(ChitGroup.created_at.desc(), ChitGroup.id.desc())
    ).all()
    return [serialize_group(group) for group in groups]


def _can_access_private_group_by_code(
    db: Session,
    *,
    group: ChitGroup,
    current_user: CurrentUser | None,
) -> bool:
    if current_user is None:
        return False

    if current_user.owner is not None and group.owner_id == current_user.owner.id:
        return True

    if current_user.subscriber is None:
        return False

    membership = db.scalar(
        select(GroupMembership.id).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == current_user.subscriber.id,
            GroupMembership.membership_status.in_(("active", "approved", "invited")),
        )
    )
    return membership is not None


def list_chits_by_code(
    db: Session,
    group_code: str,
    current_user: CurrentUser | None = None,
) -> list[dict]:
    normalized_group_code = str(group_code or "").strip()
    if not normalized_group_code:
        return []

    groups = db.scalars(
        select(ChitGroup)
        .where(
            func.lower(ChitGroup.group_code) == normalized_group_code.lower(),
            ChitGroup.status == "active",
        )
        .order_by(ChitGroup.created_at.desc(), ChitGroup.id.desc())
    ).all()
    visible_groups: list[ChitGroup] = []
    private_match_exists = False
    for group in groups:
        if group.visibility != "private":
            visible_groups.append(group)
            continue
        private_match_exists = True
        if _can_access_private_group_by_code(db, group=group, current_user=current_user):
            visible_groups.append(group)

    if private_match_exists and not visible_groups:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    return [serialize_group(group) for group in visible_groups]


def _get_group_or_404(db: Session, group_id: int) -> ChitGroup:
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


def _next_member_no(db: Session, group: ChitGroup) -> int:
    taken_numbers = set(
        db.scalars(
            select(GroupMembership.member_no).where(
                GroupMembership.group_id == group.id,
                GroupMembership.member_no >= 1,
            )
        ).all()
    )
    for member_no in range(1, int(group.member_count) + 1):
        if member_no not in taken_numbers:
            return member_no
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full")


def _activate_membership(db: Session, *, group: ChitGroup, membership: GroupMembership) -> dict:
    membership.membership_status = "active"
    membership.can_bid = True
    created_slots = create_membership_slots(
        db,
        membership,
        slot_count=1,
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
    db.commit()
    db.refresh(membership)
    slot_summary = sync_membership_slot_state(db, membership)
    return _serialize_membership(membership, slot_summary=slot_summary)


def _reject_membership_record(membership: GroupMembership) -> dict:
    membership.membership_status = "rejected"
    membership.can_bid = False
    membership.member_no = -membership.id
    return _serialize_membership_request_record(membership)


def request_membership(db: Session, group_id: int, current_user: CurrentUser) -> dict:
    subscriber = require_subscriber(current_user)
    group = _get_group_or_404(db, group_id)
    if group.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is not active")

    existing_membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )

    if existing_membership is not None:
        if existing_membership.membership_status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")
        if existing_membership.membership_status == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership request is already pending")
        if existing_membership.membership_status == "invited":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership invite is already pending")
        existing_membership.member_no = _next_member_no(db, group)
        existing_membership.membership_status = "pending"
        existing_membership.can_bid = False
        db.commit()
        db.refresh(existing_membership)
        return _serialize_membership_request_record(existing_membership)

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=_next_member_no(db, group),
        membership_status="pending",
        prized_status="unprized",
        can_bid=False,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _serialize_membership_request_record(membership)


def invite_subscriber(db: Session, group_id: int, phone: str, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")
    if group.visibility != "private":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invites are only supported for private groups")

    normalized_phone = str(phone or "").strip()
    if not normalized_phone:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Phone number is required")

    subscriber = db.scalar(select(Subscriber).where(Subscriber.phone == normalized_phone))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    if subscriber.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscriber is not active")

    existing_membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    if existing_membership is not None:
        if existing_membership.membership_status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")
        if existing_membership.membership_status == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership request is already pending")
        if existing_membership.membership_status == "invited":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership invite is already pending")
        existing_membership.member_no = _next_member_no(db, group)
        existing_membership.membership_status = "invited"
        existing_membership.can_bid = False
        db.commit()
        db.refresh(existing_membership)
        return _serialize_membership_request_record(existing_membership)

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=_next_member_no(db, group),
        membership_status="invited",
        prized_status="unprized",
        can_bid=False,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _serialize_membership_request_record(membership)


def _resolve_pending_membership_for_owner(
    db: Session,
    *,
    group_id: int,
    membership_id: int,
    current_user: CurrentUser,
) -> tuple[ChitGroup, GroupMembership]:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.id == membership_id,
            GroupMembership.group_id == group.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership request not found")
    if membership.membership_status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership request is not pending")
    return group, membership


def approve_membership_request(db: Session, group_id: int, membership_id: int, current_user: CurrentUser) -> dict:
    group, membership = _resolve_pending_membership_for_owner(
        db,
        group_id=group_id,
        membership_id=membership_id,
        current_user=current_user,
    )
    return _activate_membership(db, group=group, membership=membership)


def reject_membership_request(db: Session, group_id: int, membership_id: int, current_user: CurrentUser) -> dict:
    group, membership = _resolve_pending_membership_for_owner(
        db,
        group_id=group_id,
        membership_id=membership_id,
        current_user=current_user,
    )
    payload = _reject_membership_record(membership)
    db.commit()
    return payload


def _resolve_invited_membership_for_subscriber(
    db: Session,
    *,
    group_id: int,
    membership_id: int,
    current_user: CurrentUser,
) -> tuple[ChitGroup, GroupMembership]:
    subscriber = require_subscriber(current_user)
    group = _get_group_or_404(db, group_id)
    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.id == membership_id,
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership invite not found")
    if membership.membership_status != "invited":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership invite is not pending")
    invite_status, _invite_expires_at = resolve_invite_status(membership)
    if invite_status == "expired":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership invite has expired")
    return group, membership


def accept_membership_invite(db: Session, group_id: int, membership_id: int, current_user: CurrentUser) -> dict:
    group, membership = _resolve_invited_membership_for_subscriber(
        db,
        group_id=group_id,
        membership_id=membership_id,
        current_user=current_user,
    )
    mark_group_invite_accepted(db, group=group, membership=membership, current_user=current_user)
    return _activate_membership(db, group=group, membership=membership)


def reject_membership_invite(db: Session, group_id: int, membership_id: int, current_user: CurrentUser) -> dict:
    group, membership = _resolve_invited_membership_for_subscriber(
        db,
        group_id=group_id,
        membership_id=membership_id,
        current_user=current_user,
    )
    payload = _reject_membership_record(membership)
    mark_group_invite_rejected(db, group=group, membership=membership)
    db.commit()
    return payload


def list_owner_membership_requests(db: Session, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    memberships = db.scalars(
        select(GroupMembership)
        .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
        .where(
            ChitGroup.owner_id == owner.id,
            GroupMembership.membership_status == "pending",
        )
        .order_by(GroupMembership.joined_at.desc(), GroupMembership.id.desc())
    ).all()
    subscriber_ids = [membership.subscriber_id for membership in memberships]
    subscribers = db.scalars(select(Subscriber).where(Subscriber.id.in_(subscriber_ids))).all() if subscriber_ids else []
    subscribers_by_id = {subscriber.id: subscriber for subscriber in subscribers}
    groups_by_id = {
        group.id: group
        for group in db.scalars(select(ChitGroup).where(ChitGroup.id.in_([membership.group_id for membership in memberships]))).all()
    } if memberships else {}

    return [
        {
            "membershipId": membership.id,
            "groupId": membership.group_id,
            "groupCode": groups_by_id[membership.group_id].group_code,
            "groupTitle": groups_by_id[membership.group_id].title,
            "subscriberId": membership.subscriber_id,
            "subscriberName": subscribers_by_id.get(membership.subscriber_id).full_name if subscribers_by_id.get(membership.subscriber_id) else None,
            "memberNo": membership.member_no,
            "membershipStatus": membership.membership_status,
            "requestedAt": membership.joined_at,
        }
        for membership in memberships
    ]
