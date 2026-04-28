from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.models import AuctionBid, AuctionResult, AuctionSession, ChitGroup, GroupMembership, MembershipSlot, Payment, Payout
from app.core.security import hash_password
from app.models import User


def _auth_headers(client: TestClient, phone: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_my_financial_summary_uses_payments_payouts_and_dividends(app, db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="FIN-SUM-001",
        title="Financial Summary Group",
        chit_value=100000,
        installment_amount=5000,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 8, 1),
        first_auction_date=date(2026, 8, 10),
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
    db_session.add(MembershipSlot(user_id=1, group_id=group.id, slot_number=1, has_won=False))
    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="financial-summary-bid",
        bid_amount=1000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 8, 10, 10, 1, tzinfo=timezone.utc),
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
        winning_bid_amount=1000,
        dividend_pool_amount=1000,
        dividend_per_member_amount=100,
        owner_commission_amount=0,
        winner_payout_amount=99000,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 8, 10, 10, 3, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.flush()
    db_session.add_all(
        [
            Payment(
                owner_id=1,
                subscriber_id=1,
                membership_id=membership.id,
                installment_id=None,
                payment_type="membership",
                payment_method="upi",
                amount=1000,
                payment_date=date(2026, 8, 1),
                recorded_by_user_id=1,
                status="recorded",
            ),
            Payout(
                owner_id=1,
                auction_result_id=result.id,
                subscriber_id=1,
                membership_id=membership.id,
                gross_amount=100000,
                deductions_amount=96000,
                net_amount=4000,
                payout_method="auction_settlement",
                payout_date=date(2026, 8, 10),
                status="paid",
            ),
        ]
    )
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/users/me/financial-summary",
        headers=_auth_headers(client, "9999999999", "secret123"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_paid": 1000,
        "total_received": 4000,
        "dividend": 100,
        "net": 3100,
        "netPosition": 3000,
    }


def test_user_dashboard_supports_subscriber_owner_and_admin(app, db_session):
    admin = User(
        email="admin@example.com",
        phone="7777777777",
        password_hash=hash_password("adminpass"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    client = TestClient(app)

    owner_response = client.get(
        "/api/users/me/dashboard",
        headers=_auth_headers(client, "9999999999", "secret123"),
    )
    subscriber_response = client.get(
        "/api/users/me/dashboard",
        headers=_auth_headers(client, "8888888888", "pass123"),
    )
    admin_response = client.get(
        "/api/users/me/dashboard",
        headers=_auth_headers(client, "7777777777", "adminpass"),
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["role"] == "owner"
    assert "owner_dashboard" in owner_response.json()["stats"]
    assert "subscriber_dashboard" in owner_response.json()["stats"]
    assert "netPosition" in owner_response.json()["financial_summary"]

    assert subscriber_response.status_code == 200
    assert subscriber_response.json()["role"] == "subscriber"
    assert "subscriber_dashboard" in subscriber_response.json()["stats"]
    assert "netPosition" in subscriber_response.json()["financial_summary"]

    assert admin_response.status_code == 200
    assert admin_response.json()["role"] == "admin"
    assert "admin_summary" in admin_response.json()["stats"]
    assert "netPosition" in admin_response.json()["financial_summary"]


def test_subscriber_dashboard_allows_owner_with_subscriber_profile(app):
    client = TestClient(app)
    response = client.get(
        "/api/subscribers/dashboard",
        headers=_auth_headers(client, "9999999999", "secret123"),
    )

    assert response.status_code == 200
    assert response.json()["subscriberId"] == 1
