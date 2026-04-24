from datetime import date, datetime, timedelta, timezone
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.modules.auctions.service as auction_service
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    AuctionBid,
    AuctionResult,
    AuctionSession,
    ChitGroup,
    FinalizeJob,
    GroupMembership,
    Installment,
    LedgerEntry,
    Owner,
    Payment,
    Payout,
    Subscriber,
    User,
)
from app.modules.auctions.service import persist_auction_result


def _owner_headers(client: TestClient, phone: str = "9999999999", password: str = "secret123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _admin_headers(client: TestClient, phone: str = "7777777777", password: str = "admin-secret") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_live_auction(db_session):
    current_window_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    group = ChitGroup(
        owner_id=1,
        group_code="OPS-AUC-001",
        title="Ops Auction Group",
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
        scheduled_start_at=current_window_start,
        actual_start_at=current_window_start,
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(membership)
    return session, membership


def _seed_payment_target(db_session):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="OPS-PAY-001",
        title="Ops Payment Group",
        chit_value=10000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
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

    installment = Installment(
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
    db_session.add(installment)
    db_session.commit()
    return membership, installment


def _create_admin_user(db_session):
    admin_user = User(
        email="admin@example.com",
        phone="7777777777",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()
    return admin_user


def _wait_for_payout(db_session, auction_result_id: int, *, attempts: int = 100):
    for _ in range(attempts):
        db_session.expire_all()
        payout = db_session.scalar(select(Payout).where(Payout.auction_result_id == auction_result_id))
        if payout is not None:
            return payout
        time.sleep(0.01)
    return db_session.scalar(select(Payout).where(Payout.auction_result_id == auction_result_id))


def test_finalize_job_retries_transient_failure_and_marks_done(app, db_session, monkeypatch):
    session, membership = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="ops-finalize-retry",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)
    persist_auction_result(
        db_session,
        session=session,
        winning_bid=winning_bid,
        winner_membership_id=membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=5000,
        dividend_per_member_amount=250,
        owner_commission_amount=1000,
        winner_payout_amount=194000,
    )
    auction_service.ensure_finalize_job_enqueued(db_session, session.id)
    db_session.commit()

    original_ensure_payout = auction_service.ensure_auction_payout
    attempts = {"count": 0}

    def flaky_ensure_payout(*args, **kwargs):
        if attempts["count"] == 0:
            attempts["count"] += 1
            raise RuntimeError("temporary payout failure")
        return original_ensure_payout(*args, **kwargs)

    monkeypatch.setattr(auction_service, "ensure_auction_payout", flaky_ensure_payout)

    processed = auction_service.process_pending_finalize_jobs(db_session, auction_id=session.id, limit=2)

    assert len(processed) == 1
    db_session.expire_all()
    job = db_session.scalar(select(FinalizeJob).where(FinalizeJob.auction_id == session.id))
    payout = db_session.scalar(
        select(Payout).join(AuctionResult, AuctionResult.id == Payout.auction_result_id).where(
            AuctionResult.auction_session_id == session.id
        )
    )
    assert job is not None
    assert job.status == "done"
    assert job.retry_count == 1
    assert job.last_error is None
    assert payout is not None


def test_reconcile_incomplete_auctions_repairs_missing_ledger_and_installment_state(app, db_session):
    client = TestClient(app)
    session, membership = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="ops-reconcile-auction",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    finalize_response = client.post(f"/api/auctions/{session.id}/finalize", headers=_owner_headers(client))
    assert finalize_response.status_code == 200

    result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    payout = _wait_for_payout(db_session, result.id)
    assert result is not None
    assert payout is not None

    payout_ledger = db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id,
        )
    )
    assert payout_ledger is not None
    db_session.delete(payout_ledger)
    db_session.commit()

    payment_membership, installment = _seed_payment_target(db_session)
    payment_response = client.post(
        "/api/payments",
        headers=_owner_headers(client),
        json={
            "ownerId": 1,
            "subscriberId": payment_membership.subscriber_id,
            "membershipId": payment_membership.id,
            "installmentId": installment.id,
            "paymentType": "installment",
            "paymentMethod": "cash",
            "amount": 1000,
            "paymentDate": "2026-05-11",
            "referenceNo": "OPS-REPAIR-001",
        },
    )
    assert payment_response.status_code == 201
    payment_id = int(payment_response.json()["id"])

    payment_ledger = db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payments",
            LedgerEntry.source_id == payment_id,
        )
    )
    payment = db_session.get(Payment, payment_id)
    assert payment_ledger is not None
    assert payment is not None
    db_session.delete(payment_ledger)
    installment = db_session.get(Installment, installment.id)
    installment.paid_amount = 0
    installment.balance_amount = installment.due_amount
    installment.status = "pending"
    installment.updated_at = utcnow()
    db_session.commit()

    repair_result = auction_service.reconcile_incomplete_auctions(db_session, limit=25)

    db_session.expire_all()
    repaired_payout_ledger = db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id,
        )
    )
    repaired_payment_ledger = db_session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payments",
            LedgerEntry.source_id == payment_id,
        )
    )
    repaired_installment = db_session.get(Installment, installment.id)
    assert session.id in repair_result["repairedAuctionIds"]
    assert payment_id in repair_result["repairedPaymentIds"]
    assert repaired_payout_ledger is not None
    assert repaired_payment_ledger is not None
    assert repaired_installment.paid_amount == 1000
    assert repaired_installment.balance_amount == 0
    assert repaired_installment.status == "paid"


def test_admin_ops_endpoints_expose_finalize_jobs_and_health(app, db_session):
    _create_admin_user(db_session)
    session, membership = _seed_live_auction(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="ops-admin-view",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    client = TestClient(app)
    client.post(f"/api/auctions/{session.id}/finalize", headers=_owner_headers(client))
    admin_headers = _admin_headers(client)

    jobs_response = client.get("/api/admin/finalize-jobs", headers=admin_headers)
    health_response = client.get("/api/admin/system-health", headers=admin_headers)

    assert jobs_response.status_code == 200
    assert health_response.status_code == 200
    assert "counts" in jobs_response.json()
    assert jobs_response.json()["counts"]["done"] >= 1
    assert health_response.json()["database"]["status"] == "up"
    assert "worker" in health_response.json()
    assert "queueBacklog" in health_response.json()
