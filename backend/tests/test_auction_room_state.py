from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_auction(
    db_session,
    *,
    session_status: str,
    with_result: bool = False,
    slot_count: int = 1,
):
    group = ChitGroup(
        owner_id=1,
        group_code="AUC-RM-001",
        title="Auction Room Group",
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
    for slot_number in range(1, slot_count + 1):
        db_session.add(
            MembershipSlot(
                user_id=1,
                group_id=group.id,
                slot_number=slot_number,
                has_won=False,
            )
        )
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status=session_status,
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    if with_result:
        winning_bid = AuctionBid(
            auction_session_id=session.id,
            membership_id=membership.id,
            bidder_user_id=1,
            idempotency_key="winning-bid",
            bid_amount=12000,
            bid_discount_amount=0,
            placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
            is_valid=True,
        )
        db_session.add(winning_bid)
        db_session.flush()

        result = AuctionResult(
            auction_session_id=session.id,
            group_id=group.id,
            cycle_no=1,
            winner_membership_id=membership.id,
            winning_bid_id=winning_bid.id,
            winning_bid_amount=12000,
            dividend_pool_amount=180000,
            dividend_per_member_amount=9000,
            owner_commission_amount=1000,
            winner_payout_amount=11000,
            finalized_by_user_id=1,
            finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        )
        db_session.add(result)

    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(membership)
    return session.id, membership.id, group.id


def test_room_disables_bidding_after_close(app, db_session):
    session_id, _membership_id, _group_id = _seed_auction(db_session, session_status="closed")
    client = TestClient(app)

    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))

    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert response.json()["canBid"] is False


def test_room_exposes_finalized_result(app, db_session):
    session_id, _membership_id, _group_id = _seed_auction(
        db_session,
        session_status="finalized",
        with_result=True,
    )
    client = TestClient(app)

    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finalized"
    assert body["canBid"] is False
    assert body["result"]["winningBidId"] is not None
    assert body["result"]["winnerMembershipId"] is not None


def test_room_exposes_finalized_no_bid_state_without_pending_result(app, db_session):
    session_id, _membership_id, _group_id = _seed_auction(
        db_session,
        session_status="finalized",
        with_result=False,
    )
    client = TestClient(app)

    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finalized"
    assert body["auctionState"] == "FINALIZED"
    assert body["canBid"] is False
    assert body["validBidCount"] == 0
    assert body["result"] is None
    assert body["finalizationMessage"] == "Auction finalized with no winner because no bids were received."


def test_room_exposes_remaining_bid_capacity_for_open_session(app, db_session):
    session_id, _membership_id, _group_id = _seed_auction(
        db_session,
        session_status="open",
        slot_count=3,
    )
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    assert session is not None
    session.scheduled_start_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.actual_start_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["myBidCount"] == 0
    assert body["myBidLimit"] == 3
    assert body["myRemainingBidCapacity"] == 3
    assert body["mySlotCount"] == 3
    assert body["myWonSlotCount"] == 0
    assert body["myRemainingSlotCount"] == 3
    assert body["slotCount"] == 3
    assert body["wonSlotCount"] == 0
    assert body["remainingSlotCount"] == 3
    assert body["canBid"] is True
