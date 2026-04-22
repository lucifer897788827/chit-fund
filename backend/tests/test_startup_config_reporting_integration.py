from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import database
from app.core.bootstrap import bootstrap_database
import app.core.config as config_module
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import Payment, Payout
from app.models.user import Owner, Subscriber, User


def _owner_auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_bootstrap_database_seeds_demo_data_in_local_environment(monkeypatch, tmp_path):
    database.init_engine(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    monkeypatch.setattr(config_module.settings, "app_env", "development")

    database.Base.metadata.create_all(bind=database.engine)
    bootstrap_database()

    with database.SessionLocal() as db:
        owner_user = db.scalar(select(User).where(User.phone == "9999999999"))
        subscriber_user = db.scalar(select(User).where(User.phone == "8888888888"))
        owner = db.scalar(select(Owner).where(Owner.user_id == owner_user.id)) if owner_user else None
        subscriber = (
            db.scalar(select(Subscriber).where(Subscriber.user_id == subscriber_user.id))
            if subscriber_user
            else None
        )

        assert owner_user is not None
        assert subscriber_user is not None
        assert owner is not None
        assert subscriber is not None
        assert db.scalar(select(ChitGroup.id).where(ChitGroup.group_code == "CHIT-001")) is not None


def test_app_lifespan_bootstraps_database_before_serving(app, monkeypatch):
    from app import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "bootstrap_database", lambda: calls.append("called"))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert calls == ["called"]


def test_owner_reporting_activity_endpoint_rejects_missing_token(app):
    client = TestClient(app)

    response = client.get("/api/reporting/owner/activity")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_owner_reporting_activity_endpoint_returns_recent_activity(app, db_session):
    client = TestClient(app)
    headers = _owner_auth_headers(client)

    group = ChitGroup(
        owner_id=1,
        group_code="REP-INTEG-001",
        title="Reporting Integration Group",
        chit_value=18000,
        installment_amount=1800,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 8, 1),
        first_auction_date=date(2026, 8, 10),
        current_cycle_no=2,
        bidding_enabled=True,
        status="active",
        created_at=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=5,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=2,
        scheduled_start_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
        created_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(session)
    db_session.flush()

    payment = Payment(
        owner_id=1,
        subscriber_id=2,
        membership_id=membership.id,
        installment_id=None,
        payment_type="installment",
        payment_method="upi",
        amount=1800,
        payment_date=date(2026, 8, 11),
        reference_no="REP-INTEG-PAY-001",
        recorded_by_user_id=1,
        status="recorded",
        created_at=datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(payment)
    db_session.commit()

    response = client.get("/api/reporting/owner/activity", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["kind"] == "payment_recorded"
    assert body[0]["groupCode"] == "REP-INTEG-001"
    assert body[1]["kind"] == "auction_session"
    assert body[2]["kind"] == "group_created"


def test_owner_reporting_payouts_endpoint_returns_owner_payouts(app, db_session):
    client = TestClient(app)
    headers = _owner_auth_headers(client)

    group = ChitGroup(
        owner_id=1,
        group_code="REP-PAYOUT-001",
        title="Reporting Payout Group",
        chit_value=20000,
        installment_amount=2000,
        member_count=10,
        cycle_count=4,
        cycle_frequency="monthly",
        start_date=date(2026, 9, 1),
        first_auction_date=date(2026, 9, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
        created_at=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=8,
        membership_status="active",
        prized_status="prized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 9, 10, 10, 15, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=1,
        closed_by_user_id=1,
        created_at=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=2,
        idempotency_key="REP-PAYOUT-BID-001",
        bid_amount=6000,
        bid_discount_amount=1500,
        placed_at=datetime(2026, 9, 10, 10, 5, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()

    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=1,
        winner_membership_id=membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=6000,
        dividend_pool_amount=1500,
        dividend_per_member_amount=150,
        owner_commission_amount=350,
        winner_payout_amount=18450,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 9, 10, 10, 20, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 10, 10, 20, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.flush()

    payout = Payout(
        owner_id=1,
        auction_result_id=result.id,
        subscriber_id=2,
        membership_id=membership.id,
        gross_amount=20000,
        deductions_amount=1550,
        net_amount=18450,
        payout_method="upi",
        payout_date=date(2026, 9, 11),
        reference_no="REP-PAYOUT-001",
        status="paid",
        created_at=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(payout)
    db_session.commit()

    response = client.get("/api/reporting/owner/payouts?groupId=" + str(group.id), headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == payout.id
    assert body[0]["groupCode"] == "REP-PAYOUT-001"
    assert body[0]["netAmount"] == 18450.0


def test_owner_dashboard_activity_limit_is_capped(app, db_session):
    client = TestClient(app)
    headers = _owner_auth_headers(client)

    for index in range(105):
        db_session.add(
            ChitGroup(
                owner_id=1,
                group_code=f"REP-CAP-{index:03d}",
                title=f"Capped Reporting Group {index}",
                chit_value=10000 + index,
                installment_amount=1000,
                member_count=10,
                cycle_count=3,
                cycle_frequency="monthly",
                start_date=date(2026, 10, 1),
                first_auction_date=date(2026, 10, 10),
                current_cycle_no=1,
                bidding_enabled=True,
                status="active",
                created_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=index),
            )
        )
    db_session.commit()

    response = client.get("/api/reporting/owner/dashboard?activityLimit=500", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["recentActivity"]) == 100
    assert body["recentActivity"][0]["kind"] == "group_created"
