from datetime import date, datetime, timedelta, timezone
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import database
import app.modules.auctions.service as auction_service_module
from app.models.auction import AuctionBid, AuctionResult, AuctionSession, FinalizeJob
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.core.security import CurrentUser, hash_password
from app.models import LedgerEntry, Owner, Payout, Subscriber, User

try:
    from app.modules.auctions.service import persist_auction_result
except ImportError:  # pragma: no cover - still under active development in another slice
    persist_auction_result = None


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _owner_headers(client: TestClient, phone: str = "9999999999", password: str = "secret123") -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_live_auction(
    db_session,
    *,
    auction_mode: str = "LIVE",
    commission_mode: str = "NONE",
    commission_value: float | None = None,
    actual_start_at: datetime | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    slot_count: int = 1,
    min_bid_value: int = 0,
    max_bid_value: int | None = None,
    min_increment: int = 1,
):
    current_window_start = datetime.now(timezone.utc) - timedelta(minutes=1)
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
        scheduled_start_at=current_window_start,
        actual_start_at=actual_start_at or current_window_start,
        start_time=start_time,
        end_time=end_time,
        auction_mode=auction_mode,
        commission_mode=commission_mode,
        commission_value=commission_value,
        min_bid_value=min_bid_value,
        max_bid_value=max_bid_value if max_bid_value is not None else 200000,
        min_increment=min_increment,
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(membership)
    return session.id, membership.id, group.id


def _seed_second_owner(db_session) -> None:
    owner_user = User(
        email="other-owner@example.com",
        phone="7777777777",
        password_hash=hash_password("owner456"),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_user)
    db_session.flush()
    owner = Owner(
        user_id=owner_user.id,
        display_name="Owner Two",
        business_name="Owner Two Chits",
        city="Coimbatore",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.commit()


def _wait_for_payout(db_session, auction_result_id: int, *, timeout_seconds: float = 2.0):
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        db_session.expire_all()
        payout = db_session.scalar(select(Payout).where(Payout.auction_result_id == auction_result_id))
        if payout is not None:
            return payout
        time.sleep(0.02)
    return db_session.scalar(select(Payout).where(Payout.auction_result_id == auction_result_id))


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.get(User, 1)
    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == 1))
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def test_get_room_payload(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session, slot_count=3)
    client = TestClient(app)
    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))
    assert response.status_code == 200
    assert response.json()["sessionId"] == session_id
    assert response.json()["groupId"] == group_id
    assert response.json()["commissionMode"] == "NONE"
    assert response.json()["myMembershipId"] == membership_id
    assert response.json()["minBidValue"] == 0
    assert response.json()["maxBidValue"] == 200000
    assert response.json()["minIncrement"] == 1
    assert response.json()["myBidCount"] == 0
    assert response.json()["myBidLimit"] == 3
    assert response.json()["myRemainingBidCapacity"] == 3
    assert response.json()["mySlotCount"] == 3
    assert response.json()["myWonSlotCount"] == 0
    assert response.json()["myRemainingSlotCount"] == 3
    assert response.json()["slotCount"] == 3
    assert response.json()["wonSlotCount"] == 0
    assert response.json()["remainingSlotCount"] == 3


def test_post_bid_returns_acceptance(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "abc-123"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    bid = db_session.scalar(select(AuctionBid).where(AuctionBid.auction_session_id == session_id))
    assert bid is not None
    assert float(bid.bid_amount) == 12000.0


def test_post_bid_rejects_blank_idempotency_key(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    client = TestClient(app)

    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "   "},
    )

    assert response.status_code == 422


def test_post_bid_allows_multiple_bids_until_slot_limit(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session, slot_count=2)
    client = TestClient(app)
    headers = _subscriber_headers(client)

    first_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "multi-1"},
    )
    second_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 11000, "idempotencyKey": "multi-2"},
    )
    third_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 10000, "idempotencyKey": "multi-3"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 409
    assert third_response.json()["detail"] == "Bid limit reached for this session"

    room_response = client.get(f"/api/auctions/{session_id}/room", headers=headers)
    assert room_response.status_code == 200
    body = room_response.json()
    assert body["myBidCount"] == 2
    assert body["myBidLimit"] == 2
    assert body["myRemainingBidCapacity"] == 0
    assert body["mySlotCount"] == 2
    assert body["myWonSlotCount"] == 0
    assert body["myRemainingSlotCount"] == 2
    assert body["canBid"] is False


def test_room_keeps_slot_summary_distinct_from_bid_capacity_after_bid(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session, slot_count=2)
    client = TestClient(app)
    headers = _subscriber_headers(client)

    bid_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "slot-summary-1"},
    )

    assert bid_response.status_code == 200

    room_response = client.get(f"/api/auctions/{session_id}/room", headers=headers)

    assert room_response.status_code == 200
    body = room_response.json()
    assert body["myBidCount"] == 1
    assert body["myBidLimit"] == 2
    assert body["myRemainingBidCapacity"] == 1
    assert body["mySlotCount"] == 2
    assert body["myWonSlotCount"] == 0
    assert body["myRemainingSlotCount"] == 2
    assert body["slotCount"] == 2
    assert body["wonSlotCount"] == 0
    assert body["remainingSlotCount"] == 2


def test_post_bid_allows_multiple_blind_bids_until_slot_limit(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=1),
        end_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        slot_count=2,
    )
    client = TestClient(app)
    headers = _subscriber_headers(client)

    first_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "blind-multi-1"},
    )
    second_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 11000, "idempotencyKey": "blind-multi-2"},
    )
    third_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=headers,
        json={"membershipId": membership_id, "bidAmount": 10000, "idempotencyKey": "blind-multi-3"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 409
    assert third_response.json()["detail"] == "Bid limit reached for this session"


def test_post_bid_rejects_closed_live_auction_window(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        actual_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
    )
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    assert session is not None
    session.scheduled_start_at = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    session.actual_start_at = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    db_session.commit()

    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "live-window-closed"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Auction bidding window is closed"


def test_post_bid_rejects_fixed_mode_auction(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session, auction_mode="FIXED")
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "fixed-abc-123"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Fixed auctions do not accept bids"


def test_post_bid_rejects_amount_below_session_minimum(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        min_bid_value=10000,
        max_bid_value=20000,
        min_increment=500,
    )
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 9500, "idempotencyKey": "min-reject"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Bid amount is below minimum allowed value"


def test_post_bid_rejects_amount_above_session_maximum(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        min_bid_value=10000,
        max_bid_value=20000,
        min_increment=500,
    )
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 20500, "idempotencyKey": "max-reject"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Bid amount is above maximum allowed value"


def test_post_bid_rejects_amount_that_violates_min_increment(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        min_bid_value=10000,
        max_bid_value=20000,
        min_increment=500,
    )
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 10250, "idempotencyKey": "increment-reject"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Bid amount does not satisfy minimum increment"


def test_get_room_includes_blind_mode(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=1),
        end_time=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    client = TestClient(app)
    response = client.get(f"/api/auctions/{session_id}/room", headers=_subscriber_headers(client))

    assert response.status_code == 200
    assert response.json()["auctionMode"] == "BLIND"
    assert response.json()["commissionMode"] == "NONE"
    assert response.json()["minBidValue"] == 0
    assert response.json()["maxBidValue"] == 200000
    assert response.json()["minIncrement"] == 1
    assert response.json()["auctionState"] == "OPEN"
    assert response.json()["myMembershipId"] == membership_id


def test_persist_auction_result_updates_session_membership_and_result(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session)
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    assert session is not None

    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="finalize-1",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)

    finalized_at = datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc)
    result = persist_auction_result(
        db_session,
        session=session,
        winning_bid=winning_bid,
        winner_membership_id=membership_id,
        finalized_by_user_id=1,
        finalized_at=finalized_at,
        dividend_pool_amount=5000,
        dividend_per_member_amount=250,
        owner_commission_amount=1000,
        winner_payout_amount=194000,
    )

    db_session.refresh(session)
    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    stored_result = db_session.scalar(
        select(AuctionResult).where(AuctionResult.auction_session_id == session_id)
    )

    assert result.id == stored_result.id
    assert session.status == "closed"
    assert session.winning_bid_id == winning_bid.id
    assert session.closed_by_user_id == 1
    assert session.actual_end_at == finalized_at.replace(tzinfo=None)
    assert membership is not None
    assert membership.prized_status == "prized"
    assert membership.prized_cycle_no == session.cycle_no
    assert stored_result is not None
    assert stored_result.group_id == group_id
    assert stored_result.winner_membership_id == membership_id
    assert stored_result.winning_bid_id == winning_bid.id
    assert float(stored_result.winning_bid_amount) == 15000.0
    assert float(stored_result.dividend_pool_amount) == 5000.0
    assert float(stored_result.dividend_per_member_amount) == 250.0
    assert float(stored_result.owner_commission_amount) == 1000.0
    assert float(stored_result.winner_payout_amount) == 194000.0


def test_persist_auction_result_reassigns_previous_winner_membership(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    assert session is not None

    alternate_membership = GroupMembership(
        group_id=session.group_id,
        subscriber_id=2,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(alternate_membership)
    db_session.flush()

    first_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winner-a",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    second_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=alternate_membership.id,
        bidder_user_id=2,
        idempotency_key="winner-b",
        bid_amount=14000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([first_bid, second_bid])
    db_session.commit()
    db_session.refresh(first_bid)
    db_session.refresh(second_bid)

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=first_bid,
        winner_membership_id=membership_id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=4000,
        dividend_per_member_amount=200,
        owner_commission_amount=800,
        winner_payout_amount=195200,
    )
    persist_auction_result(
        db_session,
        session=session,
        winning_bid=second_bid,
        winner_membership_id=alternate_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 6, tzinfo=timezone.utc),
        dividend_pool_amount=4500,
        dividend_per_member_amount=225,
        owner_commission_amount=900,
        winner_payout_amount=194600,
    )

    original_membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    updated_membership = db_session.scalar(
        select(GroupMembership).where(GroupMembership.id == alternate_membership.id)
    )
    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))

    assert original_membership is not None
    assert original_membership.prized_status == "unprized"
    assert original_membership.prized_cycle_no is None
    assert updated_membership is not None
    assert updated_membership.prized_status == "prized"
    assert updated_membership.prized_cycle_no == session.cycle_no
    assert result is not None
    assert result.winner_membership_id == alternate_membership.id
    assert result.winning_bid_id == second_bid.id


def test_persist_auction_result_does_not_advance_group_twice_on_reassignment(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    assert session is not None
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    assert group is not None

    alternate_membership = GroupMembership(
        group_id=session.group_id,
        subscriber_id=2,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(alternate_membership)
    db_session.flush()

    first_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="double-advance-a",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    second_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=alternate_membership.id,
        bidder_user_id=2,
        idempotency_key="double-advance-b",
        bid_amount=13000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([first_bid, second_bid])
    db_session.commit()
    starting_cycle = group.current_cycle_no

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=first_bid,
        winner_membership_id=membership_id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=5000,
        dividend_per_member_amount=250,
        owner_commission_amount=1000,
        winner_payout_amount=194000,
    )
    db_session.refresh(group)
    assert group.current_cycle_no == starting_cycle + 1

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=second_bid,
        winner_membership_id=alternate_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 6, tzinfo=timezone.utc),
        dividend_pool_amount=5500,
        dividend_per_member_amount=275,
        owner_commission_amount=1200,
        winner_payout_amount=193800,
    )
    db_session.refresh(group)
    assert group.current_cycle_no == starting_cycle + 1


def test_finalize_auction_returns_session_summary_for_owner(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    client = TestClient(app)

    response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == session_id
    assert body["groupId"] == group_id
    assert body["status"] == "finalized"
    assert body["closedByUserId"] == 1
    assert body["finalizedByUserId"] == 1
    assert body["finalizedByName"] == "Owner One"
    assert body["finalizationMessage"] == "Auction closed and finalized."
    assert body["resultSummary"]["sessionId"] == session_id
    assert body["resultSummary"]["status"] == "finalized"
    assert body["resultSummary"]["totalBids"] == 1
    assert body["resultSummary"]["validBidCount"] == 1
    assert body["resultSummary"]["auctionResultId"] is not None
    group = db_session.get(ChitGroup, group_id)
    assert group is not None
    assert group.current_month_status == "AUCTION_DONE"


def test_finalize_auction_rejects_repeat_request_after_result_exists(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid-idempotent",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    client = TestClient(app)
    headers = _owner_headers(client)

    first_response = client.post(f"/api/auctions/{session_id}/finalize", headers=headers)
    second_response = client.post(f"/api/auctions/{session_id}/finalize", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert first_response.json()["resultSummary"]["auctionResultId"] is not None
    assert second_response.json()["detail"] == "Auction already finalized"


def test_finalize_auction_creates_payout_and_ledger_entry(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert response.status_code == 200

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None

    payout = _wait_for_payout(db_session, result.id)
    assert payout is not None
    ledger_entry = db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id,
        )
    )

    assert payout.owner_id == 1
    assert payout.subscriber_id == 1
    assert payout.membership_id == membership_id
    assert float(payout.gross_amount) == 200000.0
    assert float(payout.deductions_amount) == 21400.0
    assert float(payout.net_amount) == 178600.0
    assert payout.payout_method == "auction_settlement"
    assert payout.status == "pending"
    assert payout.payout_date is not None

    assert ledger_entry is not None
    assert ledger_entry.owner_id == 1
    assert ledger_entry.subscriber_id == 1
    assert ledger_entry.group_id == result.group_id
    assert ledger_entry.entry_type == "payout"
    assert ledger_entry.source_table == "payouts"
    assert ledger_entry.source_id == payout.id
    assert float(ledger_entry.debit_amount) == 0.0
    assert float(ledger_entry.credit_amount) == 178600.0


def test_finalize_auction_applies_percentage_commission_to_result_and_payout(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        commission_mode="PERCENTAGE",
        commission_value=10,
    )
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid-commission",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["commissionMode"] == "PERCENTAGE"
    assert body["commissionValue"] == 10.0
    assert body["resultSummary"]["ownerCommissionAmount"] == 1200.0
    assert body["resultSummary"]["winnerPayoutAmount"] == 178540.0

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None
    assert float(result.owner_commission_amount) == 1200.0

    payout = _wait_for_payout(db_session, result.id)
    assert payout is not None
    assert float(payout.deductions_amount) == 21460.0
    assert float(payout.net_amount) == 178540.0


def test_finalize_auction_rejects_repeat_request_after_payout_records_exist(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    headers = _owner_headers(client)

    first_response = client.post(f"/api/auctions/{session_id}/finalize", headers=headers)
    second_response = client.post(f"/api/auctions/{session_id}/finalize", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Auction already finalized"

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None
    payout = _wait_for_payout(db_session, result.id)
    assert payout is not None
    payout_count = db_session.scalar(
        select(func.count(Payout.id)).where(Payout.auction_result_id == result.id)
    )
    assert payout_count == 1

    ledger_count = db_session.scalar(
        select(func.count(LedgerEntry.id)).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id,
        )
    )
    assert ledger_count == 1


def test_finalize_persists_durable_job_until_worker_processes_it(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid-durable-job",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    auction_service_module.finalize_auction(db_session, session_id, _owner_current_user(db_session))

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None

    job = db_session.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == session_id))
    assert job is not None
    assert job.status in {"pending", "done"}

    processed: list[dict] = []
    if job.status == "pending":
        with database.SessionLocal() as worker_db:
            processed = auction_service_module.process_pending_finalize_jobs(
                worker_db,
                auction_id=session_id,
                limit=1,
            )

        assert len(processed) == 1
    db_session.expire_all()

    job = db_session.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == session_id))
    payout = db_session.scalar(select(Payout).where(Payout.auction_result_id == result.id))
    ledger_count = db_session.scalar(
        select(func.count(LedgerEntry.id)).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id if payout is not None else -1,
        )
    )

    assert job is not None
    assert job.status == "done"
    assert payout is not None
    assert ledger_count == 1


def test_finalize_auction_concurrent_requests_reject_duplicate_processing(app, db_session, monkeypatch):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid-concurrent",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    original_selector = auction_service_module._select_live_winning_bid_snapshot
    barrier = threading.Barrier(2)
    responses: list[int] = []

    def _synchronized_selector(db, *, session_id: int):
        snapshot = original_selector(db, session_id=session_id)
        barrier.wait(timeout=3)
        time.sleep(0.05)
        return snapshot

    def _worker():
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))
        responses.append(response.status_code)

    monkeypatch.setattr(auction_service_module, "_select_live_winning_bid_snapshot", _synchronized_selector)

    threads = [threading.Thread(target=_worker), threading.Thread(target=_worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(responses) in ([200, 200], [200, 409])
    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None
    result_count = db_session.scalar(
        select(func.count(AuctionResult.id)).where(AuctionResult.auction_session_id == session_id)
    )
    assert result_count == 1
    payout = _wait_for_payout(db_session, result.id)
    assert payout is not None
    payout_count = db_session.scalar(
        select(func.count(Payout.id)).where(Payout.auction_result_id == result.id)
    )
    assert payout_count == 1


def test_finalize_auction_rolls_back_on_write_failure(app, db_session, monkeypatch):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="winning-bid-rollback",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    def _raise_audit_failure(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(auction_service_module, "log_audit_event", _raise_audit_failure)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert response.status_code == 200
    assert response.json()["status"] == "finalizing"
    db_session.expire_all()
    session = db_session.get(AuctionSession, session_id)
    job = db_session.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == session_id))
    assert session is not None
    assert session.status == "finalizing"
    assert job is not None
    assert job.status == "pending"
    assert "audit failed" in (job.last_error or "")
    assert db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id)) is None


def test_owner_console_returns_owner_scoped_session_details(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="console-bid",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        f"/api/auctions/{session_id}/owner-console",
        headers=_owner_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == session_id
    assert body["groupTitle"] == "Auction Group"
    assert body["groupCode"] == "AUC-001"
    assert body["auctionMode"] == "LIVE"
    assert body["commissionMode"] == "NONE"
    assert body["minBidValue"] == 0
    assert body["maxBidValue"] == 200000
    assert body["minIncrement"] == 1
    assert body["validBidCount"] == 1
    assert body["totalBidCount"] == 1
    assert body["highestBidAmount"] == 11000.0
    assert body["highestBidMembershipNo"] == 1
    assert body["canFinalize"] is True


def test_owner_console_and_finalize_use_highest_valid_bid(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session)
    second_user = User(
        email="highest-bidder@example.com",
        phone="7666666666",
        password_hash="not-used",
        role="subscriber",
        is_active=True,
    )
    db_session.add(second_user)
    db_session.flush()
    second_subscriber = Subscriber(
        user_id=second_user.id,
        owner_id=1,
        full_name="Highest Bidder",
        phone=second_user.phone,
        email=second_user.email,
        status="active",
    )
    db_session.add(second_subscriber)
    db_session.flush()
    second_membership = GroupMembership(
        group_id=group_id,
        subscriber_id=second_subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(second_membership)
    db_session.flush()
    db_session.add(
        MembershipSlot(
            user_id=second_user.id,
            group_id=group_id,
            slot_number=2,
            has_won=False,
        )
    )
    db_session.commit()

    lower_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="console-lower",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    higher_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=second_membership.id,
        bidder_user_id=second_user.id,
        idempotency_key="console-higher",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([lower_bid, higher_bid])
    db_session.commit()

    client = TestClient(app)
    console_response = client.get(
        f"/api/auctions/{session_id}/owner-console",
        headers=_owner_headers(client),
    )

    assert console_response.status_code == 200
    console_body = console_response.json()
    assert console_body["highestBidAmount"] == 15000.0
    assert console_body["highestBidMembershipNo"] == 2
    assert console_body["highestBidderName"] == "Highest Bidder"

    finalize_response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert finalize_response.status_code == 200
    finalize_body = finalize_response.json()
    assert finalize_body["finalizedByName"] == "Owner One"
    assert finalize_body["resultSummary"]["auctionResultId"] is not None
    assert finalize_body["resultSummary"]["winningBidAmount"] == 15000.0
    assert finalize_body["resultSummary"]["winnerMembershipId"] == second_membership.id
    assert finalize_body["resultSummary"]["winnerMembershipNo"] == 2
    assert finalize_body["resultSummary"]["winnerName"] == "Highest Bidder"
    assert finalize_body["console"]["auctionResultId"] == finalize_body["resultSummary"]["auctionResultId"]
    assert finalize_body["console"]["highestBidAmount"] == 15000.0
    assert finalize_body["console"]["highestBidMembershipNo"] == 2
    assert finalize_body["console"]["winnerMembershipId"] == second_membership.id
    assert finalize_body["console"]["winnerMembershipNo"] == 2
    assert finalize_body["console"]["winnerName"] == "Highest Bidder"
    assert finalize_body["console"]["winningBidId"] == finalize_body["resultSummary"]["winningBidId"]

    stored_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert stored_result is not None
    assert stored_result.winning_bid_id == higher_bid.id
    assert stored_result.winner_membership_id == second_membership.id


def test_owner_console_hides_highest_bid_for_blind_mode_before_finalization(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        end_time=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="blind-console-bid",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        f"/api/auctions/{session_id}/owner-console",
        headers=_owner_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auctionMode"] == "BLIND"
    assert body["commissionMode"] == "NONE"
    assert body["minBidValue"] == 0
    assert body["maxBidValue"] == 200000
    assert body["minIncrement"] == 1
    assert body["validBidCount"] == 1
    assert body["highestBidAmount"] is None
    assert body["highestBidMembershipNo"] is None
    assert body["highestBidderName"] is None
    assert body["canFinalize"] is True
    assert body["auctionState"] == "ENDED"


def test_finalize_blind_auction_returns_console_snapshot_with_revealed_highest_bid(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        end_time=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="blind-finalize-console",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=_owner_headers(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auctionMode"] == "BLIND"
    assert body["resultSummary"]["auctionResultId"] is not None
    assert body["resultSummary"]["winningBidAmount"] == 11000.0
    assert body["console"]["auctionMode"] == "BLIND"
    assert body["console"]["status"] == "finalized"
    assert body["console"]["auctionResultId"] == body["resultSummary"]["auctionResultId"]
    assert body["console"]["highestBidAmount"] == 11000.0
    assert body["console"]["highestBidMembershipNo"] == 1
    assert body["console"]["winnerMembershipId"] == membership_id
    assert body["console"]["winnerMembershipNo"] == 1
    assert body["console"]["winnerName"] == "Owner One"
    assert body["console"]["winningBidId"] == body["resultSummary"]["winningBidId"]


def test_finalize_blind_auction_with_no_bids_returns_no_winner_and_does_not_create_payout(app, db_session):
    session_id, _membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        end_time=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    client = TestClient(app)
    headers = _owner_headers(client)

    console_response = client.get(
        f"/api/auctions/{session_id}/owner-console",
        headers=headers,
    )
    assert console_response.status_code == 200
    assert console_response.json()["auctionState"] == "ENDED"
    assert console_response.json()["canFinalize"] is True

    response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auctionMode"] == "BLIND"
    assert body["status"] == "finalized"
    assert (
        body["finalizationMessage"]
        == "Auction finalized with no winner because no bids were received."
    )
    assert body["resultSummary"]["totalBids"] == 0
    assert body["resultSummary"]["validBidCount"] == 0
    assert body["resultSummary"]["auctionResultId"] is None
    assert body["resultSummary"]["winnerMembershipId"] is None
    assert body["resultSummary"]["winningBidId"] is None
    assert body["resultSummary"]["winningBidAmount"] is None
    assert body["console"]["status"] == "finalized"
    assert body["console"]["auctionState"] == "FINALIZED"
    assert body["console"]["auctionResultId"] is None
    assert body["console"]["canFinalize"] is False
    assert (
        body["console"]["finalizationMessage"]
        == "Auction finalized with no winner because no bids were received."
    )

    stored_session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    stored_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    payout_count = db_session.scalar(select(func.count(Payout.id)))

    assert stored_session is not None
    assert stored_session.status == "finalized"
    assert stored_result is None
    assert payout_count == 0


def test_finalize_blind_auction_with_no_bids_rejects_repeat_finalize(app, db_session):
    session_id, _membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        end_time=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    client = TestClient(app)
    headers = _owner_headers(client)

    first_response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=headers,
    )
    second_response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Auction already finalized"


def test_post_bid_rejects_closed_blind_auction_window(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        actual_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        start_time=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 20, 10, 1, tzinfo=timezone.utc),
    )
    client = TestClient(app)
    response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "blind-window-closed"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Auction bidding window is closed"


def test_owner_console_blocks_blind_finalize_before_end_time(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(
        db_session,
        auction_mode="BLIND",
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        start_time=datetime(2099, 7, 10, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2099, 7, 10, 10, 3, tzinfo=timezone.utc),
    )
    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="blind-finalize-early",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    console_response = client.get(
        f"/api/auctions/{session_id}/owner-console",
        headers=_owner_headers(client),
    )
    finalize_response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=_owner_headers(client),
    )

    assert console_response.status_code == 200
    assert console_response.json()["auctionState"] == "UPCOMING"
    assert console_response.json()["canFinalize"] is False
    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"] == "Auction session cannot be finalized yet"


def test_finalize_fixed_mode_creates_auto_winner_result_and_payout(app, db_session):
    session_id, membership_id, group_id = _seed_live_auction(db_session, auction_mode="FIXED")
    client = TestClient(app)

    response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["auctionMode"] == "FIXED"
    assert body["commissionMode"] == "NONE"
    assert body["status"] == "finalized"
    assert body["resultSummary"]["winningBidAmount"] == 0.0

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None
    assert result.group_id == group_id
    assert result.winner_membership_id == membership_id
    assert float(result.winning_bid_amount) == 0.0

    auto_bid = db_session.scalar(select(AuctionBid).where(AuctionBid.id == result.winning_bid_id))
    assert auto_bid is not None
    assert float(auto_bid.bid_amount) == 0.0

    payout = _wait_for_payout(db_session, result.id)
    assert payout is not None
    assert float(payout.gross_amount) == 200000.0
    assert float(payout.deductions_amount) == 10000.0
    assert float(payout.net_amount) == 190000.0


def test_finalize_fixed_mode_parallel_requests_produce_single_result(app, db_session):
    session_id, _membership_id, _group_id = _seed_live_auction(db_session, auction_mode="FIXED")
    responses: list[int] = []

    def _worker():
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(f"/api/auctions/{session_id}/finalize", headers=_owner_headers(client))
        responses.append(response.status_code)

    threads = [threading.Thread(target=_worker), threading.Thread(target=_worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(responses) in ([200, 200], [200, 409])

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))
    assert result is not None

    result_count = db_session.scalar(
        select(func.count(AuctionResult.id)).where(AuctionResult.auction_session_id == session_id)
    )
    job_count = db_session.scalar(
        select(func.count(FinalizeJob.id)).where(FinalizeJob.auction_id == session_id)
    )
    payout = _wait_for_payout(db_session, result.id)
    payout_count = db_session.scalar(
        select(func.count(Payout.id)).where(Payout.auction_result_id == result.id)
    )

    assert result_count == 1
    assert job_count == 1
    assert payout is not None
    assert payout_count == 1


def test_finalize_auction_rejects_non_owning_owner(app, db_session):
    session_id, _membership_id, _group_id = _seed_live_auction(db_session)
    _seed_second_owner(db_session)
    client = TestClient(app)

    response = client.post(
        f"/api/auctions/{session_id}/finalize",
        headers=_owner_headers(client, phone="7777777777", password="owner456"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cannot finalize another owner's auction"
