from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auction import AuctionBid, AuctionSession
from app.models.chit import GroupMembership
from app.models.user import Subscriber


def get_room(db: Session, session_id: int) -> dict:
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")

    membership = db.scalar(
        select(GroupMembership)
        .where(GroupMembership.group_id == session.group_id)
        .order_by(GroupMembership.id.asc())
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No membership found")

    last_bid = db.scalar(
        select(AuctionBid)
        .where(
            AuctionBid.auction_session_id == session.id,
            AuctionBid.membership_id == membership.id,
        )
        .order_by(AuctionBid.id.desc())
    )

    start_at = session.actual_start_at or session.scheduled_start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)

    return {
        "sessionId": session.id,
        "groupId": session.group_id,
        "status": session.status,
        "cycleNo": session.cycle_no,
        "serverTime": datetime.now(timezone.utc),
        "endsAt": start_at + timedelta(seconds=session.bidding_window_seconds),
        "canBid": membership.can_bid and membership.membership_status == "active",
        "myMembershipId": membership.id,
        "myLastBid": int(float(last_bid.bid_amount)) if last_bid else None,
    }


def place_bid(db: Session, session_id: int, membership_id: int, bid_amount: int) -> dict:
    session = db.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction session not found")
    if session.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auction session is not open")

    membership = db.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if not membership.can_bid or membership.membership_status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership is not eligible to bid")

    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == membership.subscriber_id))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    now = datetime.now(timezone.utc)
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        bid_amount=bid_amount,
        bid_discount_amount=0,
        placed_at=now,
        is_valid=True,
    )
    db.add(bid)
    db.commit()
    db.refresh(bid)

    return {
        "accepted": True,
        "bidId": bid.id,
        "placedAt": bid.placed_at,
        "sessionStatus": session.status,
    }
