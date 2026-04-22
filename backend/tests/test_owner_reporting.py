from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.audit import log_audit_event
from app.core.security import CurrentUser
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payment, Payout
from app.models.user import Owner, Subscriber, User
from app.modules.reporting.service import get_owner_dashboard_report, list_owner_activity


def _owner_current_user(db_session, phone: str = "9999999999") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_owner_dashboard_report_summarizes_current_data(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group_one = ChitGroup(
        owner_id=owner.id,
        group_code="REP-001",
        title="Reporting One",
        chit_value=10000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=2,
        bidding_enabled=True,
        status="active",
        created_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
    )
    group_two = ChitGroup(
        owner_id=owner.id,
        group_code="REP-002",
        title="Reporting Two",
        chit_value=12000,
        installment_amount=1200,
        member_count=12,
        cycle_count=4,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 2),
        first_auction_date=date(2026, 5, 11),
        current_cycle_no=1,
        bidding_enabled=True,
        status="draft",
        created_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([group_one, group_two])
    db_session.flush()

    membership_one = GroupMembership(
        group_id=group_one.id,
        subscriber_id=subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    membership_two = GroupMembership(
        group_id=group_two.id,
        subscriber_id=subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([membership_one, membership_two])
    db_session.flush()

    db_session.add_all(
        [
            Installment(
                group_id=group_one.id,
                membership_id=membership_one.id,
                cycle_no=1,
                due_date=date(2026, 5, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=400,
                balance_amount=600,
                status="partial",
            ),
            Installment(
                group_id=group_one.id,
                membership_id=membership_one.id,
                cycle_no=2,
                due_date=date(2026, 6, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=600,
                balance_amount=400,
                status="partial",
            ),
            Installment(
                group_id=group_two.id,
                membership_id=membership_two.id,
                cycle_no=1,
                due_date=date(2026, 5, 2),
                due_amount=1200,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=1200,
                status="pending",
            ),
        ]
    )

    auction_one = AuctionSession(
        group_id=group_one.id,
        cycle_no=2,
        scheduled_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=owner.user_id,
        created_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
    )
    auction_two = AuctionSession(
        group_id=group_two.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 5, 11, 10, 15, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
        created_at=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([auction_one, auction_two])
    db_session.flush()

    open_bid = AuctionBid(
        auction_session_id=auction_one.id,
        membership_id=membership_one.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="REP-OPEN-BID-001",
        bid_amount=3200,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
        is_valid=True,
    )
    finalized_bid = AuctionBid(
        auction_session_id=auction_two.id,
        membership_id=membership_two.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="REP-FINAL-BID-001",
        bid_amount=4500,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([open_bid, finalized_bid])
    db_session.flush()

    db_session.add(
        AuctionResult(
            auction_session_id=auction_two.id,
            group_id=group_two.id,
            cycle_no=auction_two.cycle_no,
            winner_membership_id=membership_two.id,
            winning_bid_id=finalized_bid.id,
            winning_bid_amount=4500,
            dividend_pool_amount=4500,
            dividend_per_member_amount=375,
            owner_commission_amount=0,
            winner_payout_amount=7500,
            finalized_by_user_id=owner.user_id,
            finalized_at=datetime(2026, 5, 11, 10, 20, tzinfo=timezone.utc),
            created_at=datetime(2026, 5, 11, 10, 20, tzinfo=timezone.utc),
        )
    )

    db_session.add_all(
        [
            Payment(
                owner_id=owner.id,
                subscriber_id=subscriber.id,
                membership_id=membership_one.id,
                installment_id=None,
                payment_type="installment",
                payment_method="upi",
                amount=1000,
                payment_date=date(2026, 5, 12),
                reference_no="REP-PAY-001",
                recorded_by_user_id=owner.user_id,
                status="recorded",
                created_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
            ),
            Payment(
                owner_id=owner.id,
                subscriber_id=subscriber.id,
                membership_id=membership_two.id,
                installment_id=None,
                payment_type="installment",
                payment_method="cash",
                amount=1200,
                payment_date=date(2026, 5, 13),
                reference_no="REP-PAY-002",
                recorded_by_user_id=owner.user_id,
                status="recorded",
                created_at=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    report = get_owner_dashboard_report(db_session, current_user, activity_limit=5)

    assert report["ownerId"] == owner.id
    assert report["groupCount"] == 2
    assert report["totalDueAmount"] == 3200
    assert report["totalPaidAmount"] == 1000
    assert report["totalOutstandingAmount"] == 1800
    assert report["paymentCount"] == 2
    assert report["groups"][0]["groupId"] == group_one.id
    assert report["groups"][0]["totalDue"] == 2000
    assert report["groups"][1]["groupId"] == group_two.id
    assert report["recentAuctions"][0]["sessionId"] == auction_two.id
    assert report["recentAuctions"][0]["winningBidAmount"] == 4500
    assert report["recentAuctions"][0]["winnerMembershipNo"] == 2
    assert report["recentAuctions"][0]["winnerName"] == subscriber.full_name
    assert report["recentAuctions"][1]["sessionId"] == auction_one.id
    assert report["recentAuctions"][1]["highestBidAmount"] == 3200
    assert report["recentAuctions"][1]["highestBidMembershipNo"] == 1
    assert report["recentAuctions"][1]["highestBidderName"] == subscriber.full_name
    assert report["recentActivity"][0]["kind"] == "payment_recorded"
    assert report["recentActivity"][0]["refId"] is not None


def test_owner_dashboard_report_includes_payout_queries(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="PAYREP-001",
        title="Payout Reporting",
        chit_value=15000,
        installment_amount=1500,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 7, 1),
        first_auction_date=date(2026, 7, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
        created_at=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=4,
        membership_status="active",
        prized_status="prized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 7, 10, 10, 15, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
        created_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="PAYREP-BID-001",
        bid_amount=5000,
        bid_discount_amount=1000,
        placed_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
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
        winning_bid_amount=5000,
        dividend_pool_amount=1000,
        dividend_per_member_amount=100,
        owner_commission_amount=250,
        winner_payout_amount=13750,
        finalized_by_user_id=owner.user_id,
        finalized_at=datetime(2026, 7, 10, 10, 20, tzinfo=timezone.utc),
        created_at=datetime(2026, 7, 10, 10, 20, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.flush()

    payout = Payout(
        owner_id=owner.id,
        auction_result_id=result.id,
        subscriber_id=subscriber.id,
        membership_id=membership.id,
        gross_amount=15000,
        deductions_amount=1250,
        net_amount=13750,
        payout_method="bank_transfer",
        payout_date=date(2026, 7, 11),
        reference_no="PAYREP-PO-001",
        status="paid",
        created_at=datetime(2026, 7, 11, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(payout)
    db_session.commit()

    report = get_owner_dashboard_report(db_session, current_user, activity_limit=5)

    assert report["payoutCount"] == 1
    assert report["totalPayoutAmount"] == 13750
    assert report["recentPayouts"][0]["id"] == payout.id
    assert report["recentPayouts"][0]["groupCode"] == "PAYREP-001"
    assert report["recentPayouts"][0]["netAmount"] == 13750
    assert any(item["kind"] == "payout_recorded" for item in report["recentActivity"])

    client = TestClient(app)
    response = client.get("/api/reporting/owner/payouts?page=1&pageSize=1", headers=_owner_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1


def test_owner_reporting_routes_require_owner_profile(app):
    client = TestClient(app)

    response = client.get(
        "/api/reporting/owner/dashboard",
        headers={
            "Authorization": "Bearer "
            + client.post(
                "/api/auth/login",
                json={"phone": "8888888888", "password": "pass123"},
            ).json()["access_token"],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Owner profile required"


def test_owner_reporting_activity_endpoint_returns_recent_activity(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="REP-ACT-001",
        title="Activity Group",
        chit_value=9000,
        installment_amount=900,
        member_count=9,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 6, 1),
        first_auction_date=date(2026, 6, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(group)
    db_session.commit()

    activity = list_owner_activity(db_session, current_user, limit=3)

    assert activity[0]["kind"] == "group_created"
    assert activity[0]["groupCode"] == "REP-ACT-001"

    client = TestClient(app)
    response = client.get("/api/reporting/owner/activity?page=1&pageSize=1", headers=_owner_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1


def test_owner_reporting_audit_logs_endpoint_returns_recent_audit_logs(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    log_audit_event(
        db_session,
        action="payment.recorded",
        entity_type="payment",
        entity_id="501",
        actor_user_id=owner.user_id,
        owner_id=owner.id,
        metadata={"amount": 5000, "paymentId": 501},
        before={"status": "pending"},
        after={"status": "recorded"},
    )
    db_session.commit()

    report = get_owner_dashboard_report(db_session, current_user, activity_limit=5)
    assert report["recentAuditLogs"][0]["action"] == "payment.recorded"
    assert report["recentAuditLogs"][0]["before"]["status"] == "pending"
    assert report["recentAuditLogs"][0]["after"]["status"] == "recorded"

    client = TestClient(app)
    response = client.get("/api/reporting/owner/audit-logs?page=1&pageSize=1", headers=_owner_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "payment.recorded"
    assert body["items"][0]["before"]["status"] == "pending"
    assert body["items"][0]["after"]["status"] == "recorded"


def test_owner_dashboard_report_includes_penalty_breakdown_in_group_totals(app, db_session, monkeypatch):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="REP-PEN-001",
        title="Reporting Penalty",
        chit_value=10000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        penalty_enabled=True,
        penalty_type="FIXED",
        penalty_value=250,
        grace_period_days=1,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    db_session.add(
        Installment(
            group_id=group.id,
            membership_id=membership.id,
            cycle_no=1,
            due_date=date(2026, 5, 1),
            due_amount=1000,
            penalty_amount=0,
            paid_amount=0,
            balance_amount=1000,
            status="pending",
        )
    )
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc))
    report = get_owner_dashboard_report(db_session, current_user, activity_limit=5)

    assert report["totalDueAmount"] == 1250
    assert report["totalOutstandingAmount"] == 1250
    assert report["groups"][0]["totalPenaltyAmount"] == 250
    assert report["groups"][0]["penaltyEnabled"] is True


def test_owner_dashboard_report_uses_derived_state_for_expired_blind_sessions(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="REP-BLIND-001",
        title="Blind Reporting",
        chit_value=20000,
        installment_amount=2000,
        member_count=10,
        cycle_count=5,
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
        member_no=1,
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
        opened_by_user_id=owner.user_id,
        created_at=datetime(2026, 4, 20, 9, 30, tzinfo=timezone.utc),
    )
    db_session.add(ended_blind_session)
    db_session.commit()

    report = get_owner_dashboard_report(db_session, current_user, activity_limit=5)

    assert report["groups"][0]["groupId"] == group.id
    assert report["groups"][0]["openAuctionCount"] == 0
    assert report["recentAuctions"][0]["sessionId"] == ended_blind_session.id
    assert report["recentAuctions"][0]["auctionMode"] == "BLIND"
    assert report["recentAuctions"][0]["status"] == "ended"
    assert report["recentAuctions"][0]["highestBidAmount"] is None
    assert report["recentAuctions"][0]["winningBidAmount"] is None
