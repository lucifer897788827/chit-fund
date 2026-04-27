from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.security import CurrentUser, forbid_admin_chit_participation, require_owner, require_subscriber
from app.core.time import utcnow
from app.models.auction import AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, membership_can_bid
from app.models.user import Subscriber, User
from app.modules.auctions.service import get_auction_state
from app.modules.admin.cache import invalidate_admin_users_cache
from app.modules.groups.slot_service import sync_membership_slot_state
from app.modules.payments.installment_service import build_membership_dues_snapshot_map
from app.modules.subscribers.auth_service import create_subscriber_user
from app.modules.subscribers.validation import validate_subscriber_creation


MAX_RECENT_AUCTION_OUTCOMES = 5
OWNER_PARTICIPANT_ROLES = {"owner", "chit_owner"}
CHIT_PARTICIPANT_ROLES = {"subscriber", "owner", "chit_owner"}


def ensure_subscriber_profile(db: Session, current_user: CurrentUser):
    forbid_admin_chit_participation(
        current_user,
        detail="Admin cannot have subscriber profile",
    )
    if current_user.user.role not in CHIT_PARTICIPANT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber profile required")

    if current_user.subscriber is not None:
        return current_user.subscriber

    if current_user.owner is None or current_user.user.role not in OWNER_PARTICIPANT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber profile required")

    owner = require_owner(current_user)
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == current_user.user.id))
    if subscriber is None:
        display_name = owner.display_name.strip() if isinstance(owner.display_name, str) else ""
        full_name = display_name or current_user.user.phone
        subscriber = Subscriber(
            user_id=current_user.user.id,
            owner_id=owner.id,
            full_name=full_name,
            phone=current_user.user.phone,
            email=current_user.user.email,
            status="active",
            auto_created=True,
        )
        db.add(subscriber)
        db.commit()
        db.refresh(subscriber)
        invalidate_admin_users_cache()

    current_user.subscriber = subscriber
    return subscriber


def deactivate_admin_subscriber_profiles(db: Session) -> int:
    admin_user_ids = select(User.id).where(User.role == "admin")
    result = db.execute(
        update(Subscriber)
        .where(
            Subscriber.user_id.in_(admin_user_ids),
            Subscriber.status != "inactive",
        )
        .values(status="inactive")
    )
    updated_count = int(result.rowcount or 0)
    if updated_count:
        db.commit()
        invalidate_admin_users_cache()
    return updated_count


def create_subscriber(db: Session, payload, current_user: CurrentUser | None = None):
    if current_user is not None:
        owner = require_owner(current_user)
        if payload.ownerId is not None and payload.ownerId != owner.id:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create subscribers for another owner")
        payload.ownerId = owner.id

    context = validate_subscriber_creation(db, payload)
    user = create_subscriber_user(payload)
    db.add(user)
    db.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=context.owner_id,
        full_name=context.full_name,
        phone=context.phone,
        email=context.email,
        status="active",
        auto_created=False,
    )
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    invalidate_admin_users_cache()
    return {
        "id": subscriber.id,
        "ownerId": subscriber.owner_id,
        "fullName": subscriber.full_name,
        "phone": subscriber.phone,
        "email": subscriber.email,
        "status": subscriber.status,
    }


def get_subscriber_dashboard(db: Session, current_user: CurrentUser) -> dict:
    subscriber = require_subscriber(current_user)

    membership_rows = db.execute(
        select(GroupMembership, ChitGroup)
        .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
        .where(GroupMembership.subscriber_id == subscriber.id)
        .order_by(ChitGroup.id.asc(), GroupMembership.id.asc())
    ).all()

    memberships_by_group_id: dict[int, GroupMembership] = {}
    groups_by_id: dict[int, ChitGroup] = {}
    memberships: list[dict] = []

    for membership, group in membership_rows:
        memberships_by_group_id[group.id] = membership
        groups_by_id[group.id] = group

    group_sessions: list[AuctionSession] = []
    if groups_by_id:
        group_sessions = db.scalars(
            select(AuctionSession)
            .where(
                AuctionSession.group_id.in_(list(groups_by_id.keys()))
            )
            .order_by(
                AuctionSession.group_id.asc(),
                AuctionSession.cycle_no.desc(),
                AuctionSession.id.desc(),
            )
        ).all()

    group_session_result_ids = set(
        db.scalars(
            select(AuctionResult.auction_session_id).where(
                AuctionResult.auction_session_id.in_([session.id for session in group_sessions])
            )
        ).all()
    ) if group_sessions else set()
    now = utcnow()
    session_state_by_id = {
        session.id: get_auction_state(
            session,
            now=now,
            has_result=session.id in group_session_result_ids,
        )
        for session in group_sessions
    }
    latest_session_by_group_id: dict[int, AuctionSession] = {}
    for session in group_sessions:
        latest_session_by_group_id.setdefault(session.group_id, session)
    membership_ids = [membership.id for membership, _group in membership_rows]
    dues_snapshot_map = build_membership_dues_snapshot_map(db, membership_ids)

    for membership, group in membership_rows:
        latest_session = latest_session_by_group_id.get(group.id)
        auction_status = None
        if latest_session is not None:
            auction_status = session_state_by_id.get(latest_session.id, "UNKNOWN").lower()
        slot_summary = sync_membership_slot_state(db, membership)
        dues_snapshot = dues_snapshot_map.get(membership.id)
        financials = dues_snapshot.as_dict() if dues_snapshot is not None else {}
        membership_payload = {
            "membershipId": membership.id,
            "groupId": group.id,
            "groupCode": group.group_code,
            "groupTitle": group.title,
            "memberNo": membership.member_no,
            "membershipStatus": membership.membership_status,
            "prizedStatus": membership.prized_status,
            "canBid": membership_can_bid(membership),
            "currentCycleNo": group.current_cycle_no,
            "installmentAmount": money_int(group.installment_amount),
            "totalDue": financials.get("totalDue", 0.0),
            "totalPaid": financials.get("totalPaid", 0.0),
            "outstandingAmount": financials.get("outstandingAmount", 0.0),
            "paymentStatus": financials.get("paymentStatus", "FULL"),
            "arrearsAmount": financials.get("arrearsAmount", 0.0),
            "nextDueAmount": financials.get("nextDueAmount", 0.0),
            "nextDueDate": financials.get("nextDueDate"),
            "auctionStatus": auction_status,
            "slotCount": slot_summary.total_slots,
            "wonSlotCount": slot_summary.won_slots,
            "remainingSlotCount": slot_summary.available_slots,
        }
        if "penaltyAmount" in financials:
            membership_payload["penaltyAmount"] = financials["penaltyAmount"]
        memberships.append(membership_payload)

    active_auctions = []
    for session in group_sessions:
        if session_state_by_id.get(session.id) != "OPEN":
            continue
        membership = memberships_by_group_id.get(session.group_id)
        group = groups_by_id.get(session.group_id)
        if membership is None or group is None:
            continue
        if membership.membership_status != "active":
            continue
        slot_summary = sync_membership_slot_state(db, membership)
        active_auctions.append(
            {
                "sessionId": session.id,
                "groupId": group.id,
                "groupCode": group.group_code,
                "groupTitle": group.title,
                "cycleNo": session.cycle_no,
                "status": "open",
                "membershipId": membership.id,
                "canBid": slot_summary.can_bid,
                "slotCount": slot_summary.total_slots,
                "wonSlotCount": slot_summary.won_slots,
                "remainingSlotCount": slot_summary.available_slots,
            }
        )

    recent_auction_outcomes = []
    if groups_by_id:
        outcome_rows = db.execute(
            select(AuctionSession, AuctionResult)
            .join(AuctionResult, AuctionResult.auction_session_id == AuctionSession.id)
            .where(AuctionSession.group_id.in_(list(groups_by_id.keys())))
            .order_by(AuctionResult.finalized_at.desc(), AuctionSession.id.desc())
            .limit(MAX_RECENT_AUCTION_OUTCOMES)
        ).all()
        winner_membership_ids = [result.winner_membership_id for _session, result in outcome_rows]
        winner_memberships = (
            db.scalars(select(GroupMembership).where(GroupMembership.id.in_(winner_membership_ids))).all()
            if winner_membership_ids
            else []
        )
        winner_memberships_by_id = {
            membership.id: membership
            for membership in winner_memberships
        }
        winner_subscriber_ids = [membership.subscriber_id for membership in winner_memberships]
        winner_subscribers = (
            db.scalars(select(Subscriber).where(Subscriber.id.in_(winner_subscriber_ids))).all()
            if winner_subscriber_ids
            else []
        )
        winner_names_by_subscriber_id = {
            winner.id: winner.full_name
            for winner in winner_subscribers
        }

        for session, result in outcome_rows:
            group = groups_by_id.get(session.group_id)
            winner_membership = winner_memberships_by_id.get(result.winner_membership_id)
            viewer_membership = memberships_by_group_id.get(session.group_id)
            if group is None:
                continue
            recent_auction_outcomes.append(
                {
                    "sessionId": session.id,
                    "groupId": group.id,
                    "groupCode": group.group_code,
                    "groupTitle": group.title,
                    "cycleNo": session.cycle_no,
                    "status": get_auction_state(session, now=now, has_result=True).lower(),
                    "membershipId": viewer_membership.id if viewer_membership is not None else None,
                    "winnerMembershipId": result.winner_membership_id,
                    "winnerMemberNo": winner_membership.member_no if winner_membership is not None else None,
                    "winnerName": (
                        winner_names_by_subscriber_id.get(winner_membership.subscriber_id)
                        if winner_membership is not None
                        else None
                    ),
                    "winningBidAmount": money_int(result.winning_bid_amount),
                    "finalizedAt": result.finalized_at,
                }
            )

    return {
        "subscriberId": subscriber.id,
        "memberships": memberships,
        "activeAuctions": active_auctions,
        "recentAuctionOutcomes": recent_auction_outcomes,
    }
