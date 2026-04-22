from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import Payment


def _auth_headers(client: TestClient, phone: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_protected_routes_reject_missing_token(app):
    client = TestClient(app)

    response = client.post(
        "/api/payments",
        json={
            "ownerId": 1,
            "subscriberId": 2,
            "membershipId": None,
            "installmentId": None,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 25000,
            "paymentDate": "2026-05-10",
            "referenceNo": "UPI-001",
        },
    )

    assert response.status_code == 401


def test_cross_user_bid_uses_logged_in_membership(app, db_session, monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        "app.modules.auctions.service.utcnow",
        lambda: datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
    )

    group = ChitGroup(
        owner_id=1,
        group_code="SEC-001",
        title="Secure Auction",
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

    owner_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=1,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    subscriber_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([owner_membership, subscriber_membership])
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

    headers = _auth_headers(client, "8888888888", "pass123")
    response = client.post(
        f"/api/auctions/{session.id}/bids",
        headers=headers,
        json={
            "membershipId": owner_membership.id,
            "bidAmount": 12000,
            "idempotencyKey": "bid-cross-user",
        },
    )

    assert response.status_code == 200
    bid = db_session.scalar(select(AuctionBid).where(AuctionBid.auction_session_id == session.id))
    assert bid is not None
    assert bid.membership_id == subscriber_membership.id
    assert bid.bidder_user_id == 2


def test_duplicate_bid_with_same_idempotency_key_returns_single_record(app, db_session, monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        "app.modules.auctions.service.utcnow",
        lambda: datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
    )

    group = ChitGroup(
        owner_id=1,
        group_code="SEC-002",
        title="Idempotent Auction",
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
        subscriber_id=2,
        member_no=2,
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

    headers = _auth_headers(client, "8888888888", "pass123")
    first = client.post(
        f"/api/auctions/{session.id}/bids",
        headers=headers,
        json={
            "membershipId": membership.id,
            "bidAmount": 12000,
            "idempotencyKey": "duplicate-bid-key",
        },
    )
    second = client.post(
        f"/api/auctions/{session.id}/bids",
        headers=headers,
        json={
            "membershipId": membership.id,
            "bidAmount": 12000,
            "idempotencyKey": "duplicate-bid-key",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["bidId"] == second.json()["bidId"]
    bids = db_session.scalars(select(AuctionBid).where(AuctionBid.auction_session_id == session.id)).all()
    assert len(bids) == 1


def test_payments_require_auth(app):
    client = TestClient(app)

    response = client.post(
        "/api/payments",
        json={
            "ownerId": 1,
            "subscriberId": 2,
            "membershipId": None,
            "installmentId": None,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 25000,
            "paymentDate": "2026-05-10",
            "referenceNo": "UPI-001",
        },
    )

    assert response.status_code == 401
