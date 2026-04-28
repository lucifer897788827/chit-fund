from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_owner
from app.core.time import utcnow
from app.models.chit import ChitGroup, GroupInvite, GroupMembership
from app.models.user import Owner, Subscriber
from app.modules.groups.slot_service import get_next_member_no

INVITE_EXPIRY_DAYS = 7


def _get_group_or_404(db: Session, group_id: int) -> ChitGroup:
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


def _get_subscriber_or_404(db: Session, subscriber_id: int) -> Subscriber:
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == subscriber_id))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    return subscriber


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invite_expires_at(issued_at: datetime) -> datetime:
    return _ensure_utc(issued_at) + timedelta(days=INVITE_EXPIRY_DAYS)


def resolve_invite_status(membership: GroupMembership | None) -> tuple[str | None, object | None]:
    if membership is None:
        return None, None
    if membership.membership_status == "invited":
        expires_at = _invite_expires_at(membership.joined_at)
        if utcnow() >= expires_at:
            return "expired", expires_at
        return "pending", expires_at
    if membership.membership_status == "active":
        return "accepted", None
    return None, None


def _get_group_owner_user_id(db: Session, *, group: ChitGroup) -> int:
    owner_user_id = db.scalar(select(Owner.user_id).where(Owner.id == group.owner_id))
    if owner_user_id is None:
        raise ValueError(f"Owner {group.owner_id} does not exist for group {group.id}")
    return int(owner_user_id)


def _expire_pending_invites(
    db: Session,
    *,
    group_id: int | None = None,
    membership_id: int | None = None,
) -> None:
    statement = select(GroupInvite).where(GroupInvite.status == "pending")
    if group_id is not None:
        statement = statement.where(GroupInvite.group_id == group_id)
    if membership_id is not None:
        statement = statement.where(GroupInvite.membership_id == membership_id)
    now = utcnow()
    for invite in db.scalars(statement).all():
        if invite.expires_at is not None and now >= _ensure_utc(invite.expires_at):
            invite.status = "expired"
            invite.updated_at = now


def _backfill_pending_invites_for_group(db: Session, *, group: ChitGroup) -> None:
    memberships = db.scalars(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.membership_status == "invited",
        )
    ).all()
    if not memberships:
        return
    existing_membership_ids = {
        int(membership_id)
        for membership_id in db.scalars(
            select(GroupInvite.membership_id).where(
                GroupInvite.group_id == group.id,
                GroupInvite.membership_id.is_not(None),
            )
        ).all()
        if membership_id is not None
    }
    invited_by_user_id = _get_group_owner_user_id(db, group=group)
    for membership in memberships:
        if membership.id in existing_membership_ids:
            continue
        issued_at = _ensure_utc(membership.joined_at)
        db.add(
            GroupInvite(
                group_id=group.id,
                subscriber_id=membership.subscriber_id,
                membership_id=membership.id,
                invited_by_user_id=invited_by_user_id,
                status="pending",
                issued_at=issued_at,
                expires_at=_invite_expires_at(issued_at),
                created_at=issued_at,
                updated_at=issued_at,
            )
        )
    db.flush()


def _get_latest_membership_invite(
    db: Session,
    *,
    group_id: int,
    membership_id: int,
) -> GroupInvite | None:
    return db.scalar(
        select(GroupInvite)
        .where(
            GroupInvite.group_id == group_id,
            GroupInvite.membership_id == membership_id,
        )
        .order_by(GroupInvite.issued_at.desc(), GroupInvite.id.desc())
    )


def _serialize_invite_candidate(
    subscriber: Subscriber,
    *,
    membership: GroupMembership | None = None,
) -> dict:
    membership_status = membership.membership_status if membership is not None else None
    invite_status, invite_expires_at = resolve_invite_status(membership)
    member_no = membership.member_no if membership is not None and membership.member_no >= 1 else None
    invite_eligible = membership is None or membership_status == "rejected" or invite_status == "expired"
    note = None
    if membership_status == "active":
        note = "Already an active member"
    elif membership_status == "pending":
        note = "Already has a pending join request"
    elif membership_status == "invited" and invite_status == "expired":
        note = "Previous invite expired"
    elif membership_status == "invited":
        note = "Invite already sent"
    elif membership_status == "rejected":
        note = "Can be invited again"

    return {
        "subscriberId": subscriber.id,
        "userId": subscriber.user_id,
        "fullName": subscriber.full_name,
        "phone": subscriber.phone,
        "subscriberStatus": subscriber.status,
        "membershipStatus": membership_status,
        "inviteStatus": invite_status,
        "inviteExpiresAt": invite_expires_at,
        "memberNo": member_no,
        "inviteEligible": invite_eligible,
        "note": note,
    }


def _serialize_group_invite(invite: GroupInvite, *, membership: GroupMembership | None, subscriber: Subscriber) -> dict:
    member_no = membership.member_no if membership is not None and membership.member_no >= 1 else None
    return {
        "inviteId": invite.id,
        "membershipId": invite.membership_id,
        "groupId": invite.group_id,
        "subscriberId": invite.subscriber_id,
        "subscriberName": subscriber.full_name,
        "memberNo": member_no,
        "membershipStatus": membership.membership_status if membership is not None else None,
        "inviteStatus": invite.status,
        "inviteExpiresAt": invite.expires_at,
        "requestedAt": invite.issued_at,
    }


def _serialize_group_invite_audit(invite: GroupInvite, *, membership: GroupMembership | None, subscriber: Subscriber) -> dict:
    member_no = membership.member_no if membership is not None and membership.member_no >= 1 else None
    return {
        "inviteId": invite.id,
        "groupId": invite.group_id,
        "subscriberId": invite.subscriber_id,
        "subscriberName": subscriber.full_name,
        "membershipId": invite.membership_id,
        "memberNo": member_no,
        "membershipStatus": membership.membership_status if membership is not None else None,
        "status": invite.status,
        "issuedAt": invite.issued_at,
        "expiresAt": invite.expires_at,
        "acceptedAt": invite.accepted_at,
        "revokedAt": invite.revoked_at,
        "invitedByUserId": invite.invited_by_user_id,
        "revokedByUserId": invite.revoked_by_user_id,
    }


def search_group_invite_candidates(db: Session, group_id: int, query: str, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    normalized_query = str(query or "").strip()
    if len(normalized_query) < 2:
        return []

    subscribers = db.scalars(
        select(Subscriber)
        .where(
            Subscriber.status == "active",
            or_(
                Subscriber.full_name.ilike(f"%{normalized_query}%"),
                Subscriber.phone.ilike(f"%{normalized_query}%"),
            ),
        )
        .order_by(Subscriber.full_name.asc(), Subscriber.id.asc())
        .limit(10)
    ).all()
    if not subscribers:
        return []

    memberships_by_subscriber_id = {
        membership.subscriber_id: membership
        for membership in db.scalars(
            select(GroupMembership).where(
                GroupMembership.group_id == group.id,
                GroupMembership.subscriber_id.in_([subscriber.id for subscriber in subscribers]),
            )
        ).all()
    }
    return [
        _serialize_invite_candidate(subscriber, membership=memberships_by_subscriber_id.get(subscriber.id))
        for subscriber in subscribers
    ]


def create_group_invite(db: Session, group_id: int, subscriber_id: int, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")
    if (group.visibility or "private") != "private":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invites are only supported for private groups")

    _backfill_pending_invites_for_group(db, group=group)
    _expire_pending_invites(db, group_id=group.id)

    subscriber = _get_subscriber_or_404(db, subscriber_id)
    if subscriber.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscriber is not active")

    membership = db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id,
            GroupMembership.subscriber_id == subscriber.id,
        )
    )
    issued_at = utcnow()
    if membership is not None:
        if membership.membership_status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership already exists")
        if membership.membership_status == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership request is already pending")
        if membership.membership_status == "invited":
            invite_status, _current_invite_expires_at = resolve_invite_status(membership)
            if invite_status != "expired":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership invite is already pending")
        try:
            membership.member_no = membership.member_no if membership.member_no >= 1 else get_next_member_no(db, group=group)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full") from exc
        membership.membership_status = "invited"
        membership.can_bid = False
        membership.joined_at = issued_at
        membership.updated_at = issued_at
    else:
        try:
            member_no = get_next_member_no(db, group=group)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is full") from exc
        membership = GroupMembership(
            group_id=group.id,
            subscriber_id=subscriber.id,
            member_no=member_no,
            membership_status="invited",
            prized_status="unprized",
            can_bid=False,
            joined_at=issued_at,
            created_at=issued_at,
            updated_at=issued_at,
        )
        db.add(membership)
        db.flush()

    invite = GroupInvite(
        group_id=group.id,
        subscriber_id=subscriber.id,
        membership_id=membership.id,
        invited_by_user_id=current_user.user.id,
        status="pending",
        issued_at=issued_at,
        expires_at=_invite_expires_at(issued_at),
        created_at=issued_at,
        updated_at=issued_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    db.refresh(membership)
    return _serialize_group_invite(invite, membership=membership, subscriber=subscriber)


def list_group_invites(db: Session, group_id: int, current_user: CurrentUser) -> list[dict]:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    _backfill_pending_invites_for_group(db, group=group)
    _expire_pending_invites(db, group_id=group.id)
    db.commit()

    invites = db.scalars(
        select(GroupInvite)
        .where(GroupInvite.group_id == group.id)
        .order_by(GroupInvite.issued_at.desc(), GroupInvite.id.desc())
    ).all()
    memberships_by_id = {
        membership.id: membership
        for membership in db.scalars(
            select(GroupMembership).where(
                GroupMembership.id.in_([invite.membership_id for invite in invites if invite.membership_id is not None])
            )
        ).all()
    } if invites else {}
    subscribers_by_id = {
        subscriber.id: subscriber
        for subscriber in db.scalars(
            select(Subscriber).where(Subscriber.id.in_([invite.subscriber_id for invite in invites]))
        ).all()
    } if invites else {}
    return [
        _serialize_group_invite_audit(
            invite,
            membership=memberships_by_id.get(invite.membership_id),
            subscriber=subscribers_by_id[invite.subscriber_id],
        )
        for invite in invites
        if invite.subscriber_id in subscribers_by_id
    ]


def revoke_group_invite(db: Session, group_id: int, invite_id: int, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    group = _get_group_or_404(db, group_id)
    if group.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's group")

    _backfill_pending_invites_for_group(db, group=group)
    _expire_pending_invites(db, group_id=group.id)

    invite = db.scalar(
        select(GroupInvite).where(
            GroupInvite.id == invite_id,
            GroupInvite.group_id == group.id,
        )
    )
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite is no longer pending")

    membership = db.scalar(select(GroupMembership).where(GroupMembership.id == invite.membership_id)) if invite.membership_id is not None else None
    if membership is not None and membership.membership_status == "invited":
        membership.membership_status = "rejected"
        membership.can_bid = False
        membership.member_no = -membership.id
        membership.updated_at = utcnow()

    invite.status = "revoked"
    invite.revoked_at = utcnow()
    invite.revoked_by_user_id = current_user.user.id
    invite.updated_at = utcnow()
    db.commit()

    subscriber = _get_subscriber_or_404(db, invite.subscriber_id)
    return _serialize_group_invite_audit(invite, membership=membership, subscriber=subscriber)


def mark_group_invite_accepted(db: Session, *, group: ChitGroup, membership: GroupMembership, current_user: CurrentUser) -> GroupInvite | None:
    _backfill_pending_invites_for_group(db, group=group)
    _expire_pending_invites(db, group_id=group.id, membership_id=membership.id)
    invite = _get_latest_membership_invite(db, group_id=group.id, membership_id=membership.id)
    if invite is None:
        return None
    invite.status = "accepted"
    invite.accepted_at = utcnow()
    invite.updated_at = utcnow()
    return invite


def mark_group_invite_rejected(db: Session, *, group: ChitGroup, membership: GroupMembership) -> GroupInvite | None:
    _backfill_pending_invites_for_group(db, group=group)
    _expire_pending_invites(db, group_id=group.id, membership_id=membership.id)
    invite = _get_latest_membership_invite(db, group_id=group.id, membership_id=membership.id)
    if invite is None:
        return None
    invite.status = "rejected"
    invite.revoked_at = utcnow()
    invite.updated_at = utcnow()
    return invite
