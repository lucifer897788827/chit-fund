from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import LedgerEntry, Payment, Payout
from app.models.user import Owner, Subscriber, User


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_installment_target(db_session):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="PAY-API-001",
        title="Payment API Chit",
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
    return subscriber, group, membership, installment


def _seed_payout_target(db_session):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="PAYOUT-API-001",
        title="Payout API Chit",
        chit_value=20000,
        installment_amount=2000,
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
        member_no=4,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        actual_end_at=None,
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=owner.user_id,
        idempotency_key="PAYOUT-API-001",
        bid_amount=1500,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
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
        winning_bid_amount=1500,
        dividend_pool_amount=0,
        dividend_per_member_amount=0,
        owner_commission_amount=0,
        winner_payout_amount=18500,
        finalized_by_user_id=owner.user_id,
        finalized_at=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.flush()

    payout = Payout(
        owner_id=owner.id,
        auction_result_id=result.id,
        subscriber_id=subscriber.id,
        membership_id=membership.id,
        gross_amount=20000,
        deductions_amount=1500,
        net_amount=18500,
        payout_method="auction_settlement",
        payout_date=date(2026, 5, 11),
        reference_no=None,
        status="pending",
    )
    db_session.add(payout)
    db_session.commit()
    return owner, subscriber, group, membership, result, payout


def test_record_installment_payment_updates_installment_and_ledger(app, db_session):
    subscriber, group, membership, installment = _seed_installment_target(db_session)
    client = TestClient(app)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "installmentId": installment.id,
        "paymentType": "installment",
        "paymentMethod": "upi",
        "amount": 600,
        "paymentDate": "2026-05-10",
        "referenceNo": "UPI-PAY-001",
    }

    response = client.post("/api/payments", headers=_owner_headers(client), json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "recorded"
    assert body["groupId"] == group.id
    assert body["installmentStatus"] == "partial"
    assert body["installmentBalanceAmount"] == 400.0
    assert body["ledgerEntryId"] is not None

    db_session.refresh(installment)
    assert float(installment.paid_amount) == 600.0
    assert float(installment.balance_amount) == 400.0
    assert installment.status == "partial"

    payment = db_session.get(Payment, body["id"])
    ledger_entry = db_session.get(LedgerEntry, body["ledgerEntryId"])
    assert payment is not None
    assert ledger_entry is not None
    assert ledger_entry.source_table == "payments"
    assert ledger_entry.source_id == payment.id
    assert ledger_entry.group_id == group.id
    assert float(ledger_entry.debit_amount) == 600.0


def test_record_installment_payment_resolves_membership_without_installment_id(app, db_session):
    subscriber, group, membership, installment = _seed_installment_target(db_session)
    client = TestClient(app)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "paymentType": "installment",
        "paymentMethod": "upi",
        "amount": 600,
        "paymentDate": "2026-05-10",
        "referenceNo": "UPI-PAY-002",
    }

    response = client.post("/api/payments", headers=_owner_headers(client), json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["installmentId"] == installment.id
    assert body["cycleNo"] == installment.cycle_no
    assert body["installmentStatus"] == "partial"
    assert body["installmentBalanceAmount"] == 400.0

    db_session.refresh(installment)
    assert float(installment.paid_amount) == 600.0
    assert float(installment.balance_amount) == 400.0
    assert installment.status == "partial"


def test_record_installment_payment_rejects_decimal_amounts(app, db_session):
    subscriber, _group, membership, _installment = _seed_installment_target(db_session)
    client = TestClient(app)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "paymentType": "installment",
        "paymentMethod": "upi",
        "amount": 600.5,
        "paymentDate": "2026-05-10",
        "referenceNo": "UPI-PAY-DECIMAL-001",
    }

    response = client.post("/api/payments", headers=_owner_headers(client), json=payload)

    assert response.status_code == 422
    assert "Decimal values are not allowed. Use whole amounts only." in response.text


def test_payment_history_balances_and_duplicate_protection(app, db_session):
    subscriber, group, membership, installment = _seed_installment_target(db_session)
    client = TestClient(app)
    headers = _owner_headers(client)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "installmentId": installment.id,
        "paymentType": "installment",
        "paymentMethod": "cash",
        "amount": 1000,
        "paymentDate": "2026-05-11",
        "referenceNo": "CASH-PAY-001",
    }

    response = client.post("/api/payments", headers=headers, json=payload)
    assert response.status_code == 201

    duplicate_response = client.post("/api/payments", headers=headers, json=payload)
    assert duplicate_response.status_code == 409

    history_response = client.get(
        f"/api/payments?subscriberId={subscriber.id}&groupId={group.id}",
        headers=headers,
    )
    assert history_response.status_code == 200
    assert [payment["id"] for payment in history_response.json()] == [response.json()["id"]]

    paginated_history = client.get(
        f"/api/payments?subscriberId={subscriber.id}&groupId={group.id}&page=1&pageSize=1",
        headers=headers,
    )
    assert paginated_history.status_code == 200
    paginated_history_body = paginated_history.json()
    assert paginated_history_body["page"] == 1
    assert paginated_history_body["pageSize"] == 1
    assert len(paginated_history_body["items"]) == 1

    balances_response = client.get(
        f"/api/payments/balances?subscriberId={subscriber.id}&groupId={group.id}",
        headers=headers,
    )
    assert balances_response.status_code == 200
    assert balances_response.json() == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "memberNo": 1,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
            "totalDue": 1000.0,
            "totalPaid": 1000.0,
            "outstandingAmount": 0.0,
            "penaltyAmount": None,
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 0.0,
            "nextDueDate": None,
        }
    ]

    paginated_balances = client.get(
        f"/api/payments/balances?subscriberId={subscriber.id}&groupId={group.id}&page=1&pageSize=1",
        headers=headers,
    )
    assert paginated_balances.status_code == 200
    paginated_balances_body = paginated_balances.json()
    assert paginated_balances_body["page"] == 1
    assert paginated_balances_body["pageSize"] == 1
    assert len(paginated_balances_body["items"]) == 1


def test_record_membership_payment_by_cycle_updates_installment_balances_and_history(app, db_session, monkeypatch):
    subscriber, group, membership, installment = _seed_installment_target(db_session)
    installment.paid_amount = 1000
    installment.balance_amount = 0
    installment.status = "paid"
    second_installment = Installment(
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=2,
        due_date=date(2026, 6, 1),
        due_amount=1000,
        penalty_amount=0,
        paid_amount=0,
        balance_amount=1000,
        status="pending",
    )
    db_session.add(second_installment)
    db_session.commit()

    client = TestClient(app)
    headers = _owner_headers(client)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "cycleNo": 2,
        "paymentType": "membership",
        "paymentMethod": "cash",
        "amount": 400,
        "paymentDate": "2026-06-10",
        "referenceNo": "CYCLE-PAY-002",
    }

    response = client.post("/api/payments", headers=headers, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["membershipId"] == membership.id
    assert body["installmentId"] == second_installment.id
    assert body["cycleNo"] == 2
    assert body["installmentStatus"] == "partial"
    assert body["installmentBalanceAmount"] == 600.0
    assert body["paymentStatus"] == "PARTIAL"
    assert body["arrearsAmount"] == 600.0
    assert body["nextDueAmount"] == 600.0
    assert body["outstandingAmount"] == 600.0

    db_session.refresh(second_installment)
    assert float(second_installment.paid_amount) == 400.0
    assert float(second_installment.balance_amount) == 600.0
    assert second_installment.status == "partial"

    monkeypatch.setattr(
        "app.modules.payments.installment_service.utcnow",
        lambda: datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc),
    )

    history_response = client.get(
        f"/api/payments?subscriberId={subscriber.id}&groupId={group.id}",
        headers=headers,
    )
    assert history_response.status_code == 200
    history_items = history_response.json()
    assert len(history_items) == 1
    assert history_items[0]["id"] == body["id"]
    assert history_items[0]["ownerId"] == 1
    assert history_items[0]["subscriberId"] == subscriber.id
    assert history_items[0]["membershipId"] == membership.id
    assert history_items[0]["installmentId"] == second_installment.id
    assert history_items[0]["cycleNo"] == 2
    assert history_items[0]["groupId"] == group.id
    assert history_items[0]["paymentType"] == "membership"
    assert history_items[0]["paymentMethod"] == "cash"
    assert history_items[0]["amount"] == 400.0
    assert history_items[0]["paymentDate"] == "2026-06-10"
    assert history_items[0]["referenceNo"] == "CYCLE-PAY-002"
    assert history_items[0]["status"] == "recorded"
    assert history_items[0]["paymentStatus"] == "PARTIAL"
    assert history_items[0]["penaltyAmount"] is None
    assert history_items[0]["arrearsAmount"] == 600.0
    assert history_items[0]["nextDueAmount"] == 600.0
    assert history_items[0]["nextDueDate"] == "2026-06-01"
    assert history_items[0]["outstandingAmount"] == 600.0

    balances_response = client.get(
        f"/api/payments/balances?subscriberId={subscriber.id}&groupId={group.id}",
        headers=headers,
    )
    assert balances_response.status_code == 200
    assert balances_response.json() == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "memberNo": 1,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
            "totalDue": 2000.0,
            "totalPaid": 1400.0,
            "outstandingAmount": 600.0,
            "penaltyAmount": None,
            "paymentStatus": "PARTIAL",
            "arrearsAmount": 600.0,
            "nextDueAmount": 600.0,
            "nextDueDate": "2026-06-01",
        }
    ]


def test_owner_payout_listing_and_settlement(app, db_session):
    owner, subscriber, group, membership, result, payout = _seed_payout_target(db_session)
    client = TestClient(app)
    headers = _owner_headers(client)

    list_response = client.get(f"/api/payments/payouts?groupId={group.id}", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "id": payout.id,
            "ownerId": owner.id,
            "auctionResultId": result.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "groupId": group.id,
            "groupCode": group.group_code,
            "groupTitle": group.title,
            "cycleNo": 1,
            "subscriberName": subscriber.full_name,
            "memberNo": 4,
            "grossAmount": 20000.0,
            "deductionsAmount": 1500.0,
            "netAmount": 18500.0,
            "payoutMethod": "auction_settlement",
            "payoutDate": "2026-05-11",
            "referenceNo": None,
            "status": "pending",
            "paymentStatus": "FULL",
            "penaltyAmount": None,
            "arrearsAmount": 0.0,
            "nextDueAmount": 0.0,
            "nextDueDate": None,
            "outstandingAmount": 0.0,
            "createdAt": payout.created_at.isoformat(),
            "updatedAt": payout.updated_at.isoformat(),
        }
    ]

    paginated_payouts = client.get(f"/api/payments/payouts?groupId={group.id}&page=1&pageSize=1", headers=headers)
    assert paginated_payouts.status_code == 200
    paginated_payouts_body = paginated_payouts.json()
    assert paginated_payouts_body["page"] == 1
    assert paginated_payouts_body["pageSize"] == 1
    assert len(paginated_payouts_body["items"]) == 1

    filtered_response = client.get(f"/api/payments/payouts?groupId={group.id}&status=PENDING", headers=headers)
    assert filtered_response.status_code == 200
    assert filtered_response.json()[0]["id"] == payout.id

    alias_filtered_response = client.get(f"/api/payments/payouts?groupId={group.id}&status=processed", headers=headers)
    assert alias_filtered_response.status_code == 200
    assert alias_filtered_response.json()[0]["id"] == payout.id

    blank_status_response = client.get(f"/api/payments/payouts?groupId={group.id}&status=", headers=headers)
    assert blank_status_response.status_code == 200
    assert blank_status_response.json()[0]["id"] == payout.id

    settle_response = client.post(
        f"/api/payments/payouts/{payout.id}/settle",
        headers=headers,
        json={
            "referenceNo": "NEFT-SETTLE-001",
            "payoutMethod": "bank_transfer",
            "payoutDate": "2026-05-12",
        },
    )
    assert settle_response.status_code == 200
    settled = settle_response.json()
    assert settled["status"] == "settled"
    assert settled["referenceNo"] == "NEFT-SETTLE-001"
    assert settled["payoutMethod"] == "bank_transfer"
    assert settled["payoutDate"] == "2026-05-12"

    db_session.refresh(payout)
    assert payout.status == "settled"
    assert payout.reference_no == "NEFT-SETTLE-001"
    assert payout.payout_method == "bank_transfer"
    assert payout.payout_date.isoformat() == "2026-05-12"


def test_payout_listing_requires_owner_profile(app):
    client = TestClient(app)
    response = client.get(
        "/api/payments/payouts",
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


def test_record_installment_payment_returns_penalty_breakdown(app, db_session):
    subscriber, group, membership, installment = _seed_installment_target(db_session)
    group.penalty_enabled = True
    group.penalty_type = "FIXED"
    group.penalty_value = 250
    group.grace_period_days = 0
    db_session.commit()

    client = TestClient(app)
    payload = {
        "ownerId": 1,
        "subscriberId": subscriber.id,
        "membershipId": membership.id,
        "installmentId": installment.id,
        "paymentType": "installment",
        "paymentMethod": "cash",
        "amount": 500,
        "paymentDate": "2026-05-10",
        "referenceNo": "PEN-PAY-001",
    }

    response = client.post("/api/payments", headers=_owner_headers(client), json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["penaltyAmount"] == 250.0
    assert body["installmentBalanceAmount"] == 750.0
    assert body["arrearsAmount"] == 750.0
