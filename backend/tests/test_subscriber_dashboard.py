from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.service import create_auction_result
from app.models.auction import AuctionBid


def _login_subscriber(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
def test_subscriber_dashboard_returns_memberships_and_open_auctions(app, db_session, monkeypatch):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="SUB-001",
        title="Subscriber Monthly Chit",
        chit_value=150000,
        installment_amount=7500,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
        current_cycle_no=2,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=3,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    open_session = AuctionSession(
        group_id=group.id,
        cycle_no=2,
        scheduled_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 4, 20, 10, 5, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    closed_session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=1,
    )
    db_session.add(open_session)
    db_session.add(closed_session)
    db_session.commit()
    monkeypatch.setattr(
        "app.modules.subscribers.service.utcnow",
        lambda: datetime(2026, 4, 20, 10, 6, tzinfo=timezone.utc),
    )

    client = TestClient(app)
    response = client.get("/api/subscribers/dashboard", headers=_login_subscriber(client))

    assert response.status_code == 200
    body = response.json()
    assert body["subscriberId"] == subscriber.id
    assert body["memberships"] == [
        {
            "membershipId": membership.id,
            "groupId": group.id,
            "groupCode": "SUB-001",
            "groupTitle": "Subscriber Monthly Chit",
            "memberNo": 3,
            "membershipStatus": "active",
            "prizedStatus": "unprized",
            "canBid": True,
            "currentCycleNo": 2,
                "installmentAmount": 7500.0,
                "totalDue": 0.0,
                "totalPaid": 0.0,
                "outstandingAmount": 0.0,
                "penaltyAmount": None,
                "paymentStatus": "FULL",
                "arrearsAmount": 0.0,
                "nextDueAmount": 0.0,
                "nextDueDate": None,
            "auctionStatus": "open",
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
        }
    ]
    assert body["activeAuctions"] == [
        {
            "sessionId": open_session.id,
            "groupId": group.id,
            "groupCode": "SUB-001",
            "groupTitle": "Subscriber Monthly Chit",
            "cycleNo": 2,
            "status": "open",
            "membershipId": membership.id,
            "canBid": True,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
        }
    ]


def test_subscriber_dashboard_marks_prized_membership_unavailable_for_future_cycles(app, db_session, monkeypatch):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="SUB-002",
        title="Subscriber Prize Tracking",
        chit_value=150000,
        installment_amount=7500,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
        current_cycle_no=2,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=3,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    other_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=1,
        member_no=4,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([membership, other_membership])
    db_session.flush()

    finalized_session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 3, 20, 10, 3, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    future_open_session = AuctionSession(
        group_id=group.id,
        cycle_no=2,
        scheduled_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 4, 20, 10, 5, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add_all([finalized_session, future_open_session])
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=finalized_session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="winner",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 3, 20, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    create_auction_result(db_session, session_id=finalized_session.id, finalized_by_user_id=1)
    monkeypatch.setattr(
        "app.modules.subscribers.service.utcnow",
        lambda: datetime(2026, 4, 20, 10, 6, tzinfo=timezone.utc),
    )

    client = TestClient(app)
    response = client.get("/api/subscribers/dashboard", headers=_login_subscriber(client))

    assert response.status_code == 200
    body = response.json()
    assert body["memberships"][0]["prizedStatus"] == "prized"
    assert body["memberships"][0]["canBid"] is False
    assert body["memberships"][0]["slotCount"] == 1
    assert body["memberships"][0]["wonSlotCount"] == 1
    assert body["memberships"][0]["remainingSlotCount"] == 0
    assert body["activeAuctions"] == [
        {
            "sessionId": future_open_session.id,
            "groupId": group.id,
            "groupCode": "SUB-002",
            "groupTitle": "Subscriber Prize Tracking",
            "cycleNo": 2,
            "status": "open",
            "membershipId": membership.id,
            "canBid": False,
            "slotCount": 1,
            "wonSlotCount": 1,
            "remainingSlotCount": 0,
        }
    ]
    assert body["recentAuctionOutcomes"] == [
        {
            "sessionId": finalized_session.id,
            "groupId": group.id,
            "groupCode": "SUB-002",
            "groupTitle": "Subscriber Prize Tracking",
            "cycleNo": 1,
            "status": "finalized",
            "membershipId": membership.id,
            "winnerMembershipId": membership.id,
            "winnerMemberNo": 3,
            "winnerName": subscriber.full_name,
            "winningBidAmount": 10000.0,
            "finalizedAt": body["recentAuctionOutcomes"][0]["finalizedAt"],
        }
    ]


def test_subscriber_dashboard_excludes_expired_blind_no_bid_sessions_from_active_auctions(app, db_session, monkeypatch):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="SUB-BLIND-001",
        title="Blind Subscriber Group",
        chit_value=150000,
        installment_amount=7500,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=3,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    ended_blind_session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        start_time=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 20, 10, 3, tzinfo=timezone.utc),
        auction_mode="BLIND",
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(ended_blind_session)
    db_session.commit()
    monkeypatch.setattr(
        "app.modules.subscribers.service.utcnow",
        lambda: datetime(2026, 4, 20, 10, 4, tzinfo=timezone.utc),
    )

    client = TestClient(app)
    response = client.get("/api/subscribers/dashboard", headers=_login_subscriber(client))

    assert response.status_code == 200
    body = response.json()
    assert body["memberships"] == [
        {
            "membershipId": membership.id,
            "groupId": group.id,
            "groupCode": "SUB-BLIND-001",
            "groupTitle": "Blind Subscriber Group",
            "memberNo": 3,
            "membershipStatus": "active",
            "prizedStatus": "unprized",
            "canBid": True,
            "currentCycleNo": 1,
            "installmentAmount": 7500.0,
            "totalDue": 0.0,
            "totalPaid": 0.0,
            "outstandingAmount": 0.0,
            "penaltyAmount": None,
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 0.0,
            "nextDueDate": None,
            "auctionStatus": "ended",
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
        }
    ]
    assert body["activeAuctions"] == []
    assert body["recentAuctionOutcomes"] == []


def test_subscriber_dashboard_forbids_owner_without_subscriber_profile(app):
    client = TestClient(app)

    owner_user = User(
        email="owner-only@example.com",
        phone="7777000000",
        password_hash=hash_password("ownerpass"),
        role="chit_owner",
        is_active=True,
    )

    from app.core import database

    with database.SessionLocal() as db_session:
        db_session.add(owner_user)
        db_session.flush()
        owner = Owner(
            user_id=owner_user.id,
            display_name="Owner Only",
            business_name="Owner Only Chits",
            city="Madurai",
            state="Tamil Nadu",
            status="active",
        )
        db_session.add(owner)
        db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"phone": "7777000000", "password": "ownerpass"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    response = client.get(
        "/api/subscribers/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Subscriber profile required"
