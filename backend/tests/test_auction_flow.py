from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionSession
from app.models.chit import ChitGroup, GroupMembership


def _seed_live_auction(db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="AUC-001",
        title="Auction Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 7, 1),
        first_auction_date=date(2026, 7, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=1,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(membership)
    return session.id, membership.id, group.id


def test_get_room_payload(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session)
    client = TestClient(app)
    response = client.get(f"/api/auctions/{session_id}/room")
    assert response.status_code == 200
    assert response.json()["sessionId"] == session_id
    assert response.json()["groupId"] == group_id
    assert response.json()["myMembershipId"] == membership_id


def test_post_bid_returns_acceptance(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "abc-123"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    bid = db_session.scalar(select(AuctionBid).where(AuctionBid.auction_session_id == session_id))
    assert bid is not None
    assert float(bid.bid_amount) == 12000.0
