from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment, MembershipSlot
from app.models.external import ExternalChit
from app.models.money import Payment, Payout
from app.models.user import Owner, Subscriber, User


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_core_models_are_importable():
    assert User.__tablename__ == "users"
    assert Owner.__tablename__ == "owners"
    assert Subscriber.__tablename__ == "subscribers"
    assert ChitGroup.__tablename__ == "chit_groups"
    assert GroupMembership.__tablename__ == "group_memberships"
    assert MembershipSlot.__tablename__ == "membership_slots"
    assert ExternalChit.__tablename__ == "external_chits"


def test_create_subscriber_persists_profile(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/subscribers",
        headers=_owner_headers(client),
        json={
            "ownerId": 1,
            "fullName": "Subscriber Two",
            "phone": "7777777777",
            "email": "subscriber2@example.com",
            "password": "subscriber-two-pass",
        },
    )
    assert response.status_code == 201
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "7777777777"))
    assert subscriber is not None
    assert subscriber.full_name == "Subscriber Two"
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "7777777777", "password": "subscriber-two-pass"},
    )
    assert login_response.status_code == 200


def test_create_group_returns_owner_scoped_group(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "MAY-001",
            "title": "May Monthly Chit",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
        },
    )
    assert response.status_code == 201
    assert response.json()["groupCode"] == "MAY-001"
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.group_code == "MAY-001"))
    assert group is not None
    assert group.title == "May Monthly Chit"
    assert group.visibility == "private"
    assert group.penalty_enabled is False
    assert group.penalty_type is None
    assert group.penalty_value is None
    assert group.grace_period_days == 0


def test_create_group_persists_penalty_configuration(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PEN-001",
            "title": "Penalty Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
            "penaltyEnabled": True,
            "penaltyType": "PERCENTAGE",
            "penaltyValue": 7.5,
            "gracePeriodDays": 3,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["penaltyEnabled"] is True
    assert body["penaltyType"] == "PERCENTAGE"
    assert body["penaltyValue"] == 7.5
    assert body["gracePeriodDays"] == 3

    group = db_session.scalar(select(ChitGroup).where(ChitGroup.group_code == "PEN-001"))
    assert group is not None
    assert group.penalty_enabled is True
    assert group.penalty_type == "PERCENTAGE"
    assert float(group.penalty_value) == 7.5
    assert group.grace_period_days == 3


def test_create_group_accepts_public_visibility(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PUB-001",
            "title": "Public Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "visibility": "public",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
        },
    )

    assert response.status_code == 201
    assert response.json()["visibility"] == "public"
    assert response.json()["status"] == "active"
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.group_code == "PUB-001"))
    assert group is not None
    assert group.visibility == "public"
    assert group.status == "active"


def test_public_chits_endpoint_returns_only_public_active_groups(app, db_session):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    db_session.add_all(
        [
            ChitGroup(
                owner_id=owner.id,
                group_code="PUBLIC-OPEN",
                title="Public Open Group",
                chit_value=300000,
                installment_amount=15000,
                member_count=10,
                cycle_count=10,
                cycle_frequency="monthly",
                visibility="public",
                start_date=date(2026, 6, 1),
                first_auction_date=date(2026, 6, 10),
                current_cycle_no=1,
                bidding_enabled=True,
                status="active",
            ),
            ChitGroup(
                owner_id=owner.id,
                group_code="PRIVATE-HIDDEN",
                title="Private Hidden Group",
                chit_value=300000,
                installment_amount=15000,
                member_count=10,
                cycle_count=10,
                cycle_frequency="monthly",
                visibility="private",
                start_date=date(2026, 6, 1),
                first_auction_date=date(2026, 6, 10),
                current_cycle_no=1,
                bidding_enabled=True,
                status="active",
            ),
            ChitGroup(
                owner_id=owner.id,
                group_code="PUBLIC-DRAFT",
                title="Public Draft Group",
                chit_value=300000,
                installment_amount=15000,
                member_count=10,
                cycle_count=10,
                cycle_frequency="monthly",
                visibility="public",
                start_date=date(2026, 6, 1),
                first_auction_date=date(2026, 6, 10),
                current_cycle_no=1,
                bidding_enabled=True,
                status="draft",
            ),
        ]
    )
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/chits/public")

    assert response.status_code == 200
    assert [group["groupCode"] for group in response.json()] == ["PUBLIC-OPEN"]


def test_create_group_allows_zero_percentage_penalty(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PEN-000",
            "title": "Zero Percentage Penalty Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
            "penaltyEnabled": True,
            "penaltyType": "PERCENTAGE",
            "penaltyValue": 0,
            "gracePeriodDays": 3,
        },
    )

    assert response.status_code == 201
    assert response.json()["penaltyValue"] == 0.0


def test_create_group_rejects_percentage_penalty_above_hundred(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PEN-101",
            "title": "Invalid Percentage Penalty Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
            "penaltyEnabled": True,
            "penaltyType": "PERCENTAGE",
            "penaltyValue": 101,
            "gracePeriodDays": 3,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Percentage penalty value must not exceed 100"


def test_create_group_allows_fixed_integer_penalty(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PEN-FIXED",
            "title": "Fixed Penalty Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
            "penaltyEnabled": True,
            "penaltyType": "FIXED",
            "penaltyValue": 1000,
            "gracePeriodDays": 3,
        },
    )

    assert response.status_code == 201
    assert response.json()["penaltyValue"] == 1000
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.group_code == "PEN-FIXED"))
    assert group is not None
    assert int(group.penalty_value) == 1000


def test_create_group_rejects_fixed_decimal_penalty(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "PEN-FIXED-DECIMAL",
            "title": "Fixed Decimal Penalty Group",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
            "penaltyEnabled": True,
            "penaltyType": "FIXED",
            "penaltyValue": 1000.5,
            "gracePeriodDays": 3,
        },
    )

    assert response.status_code == 422
    assert "Decimal values are not allowed. Use whole amounts only." in response.text


def test_list_groups_returns_owner_groups(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "LIST-001",
            "title": "List Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    response = client.get("/api/groups", headers=headers)
    assert response.status_code == 200
    assert any(group["groupCode"] == "LIST-001" for group in response.json())


def test_list_groups_supports_pagination(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "LIST-002",
            "title": "List Group Two",
            "chitValue": 120000,
            "installmentAmount": 6000,
            "memberCount": 12,
            "cycleCount": 12,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    response = client.get("/api/groups?page=1&pageSize=1", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1


def test_close_collection_persists_group_lifecycle_state(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "CLOSE-001",
            "title": "Close Collection Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    group_id = group_response.json()["id"]

    response = client.post(f"/api/groups/{group_id}/close-collection", headers=headers)

    assert response.status_code == 200
    assert response.json()["collectionClosed"] is True
    assert response.json()["currentMonthStatus"] == "COLLECTION_CLOSED"
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    assert group is not None
    assert group.collection_closed is True
    assert group.current_month_status == "COLLECTION_CLOSED"


def test_close_collection_rejects_duplicate_close(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "CLOSE-002",
            "title": "Close Collection Duplicate Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    group_id = group_response.json()["id"]

    first_response = client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    duplicate_response = client.post(f"/api/groups/{group_id}/close-collection", headers=headers)

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Collection is already closed"


def test_close_collection_requires_owner_profile(app):
    client = TestClient(app)
    owner_headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=owner_headers,
        json={
            "ownerId": 1,
            "groupCode": "CLOSE-003",
            "title": "Close Collection Owner Only Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )

    response = client.post(
        f"/api/groups/{group_response.json()['id']}/close-collection",
        headers=_subscriber_headers(client),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Owner profile required"


def test_close_collection_requires_authentication(app):
    client = TestClient(app)

    group_response = client.post(
        "/api/groups",
        headers=_owner_headers(client),
        json={
            "ownerId": 1,
            "groupCode": "B7-AUTH-001",
            "title": "Authentication Check Group",
            "chitValue": 120000,
            "installmentAmount": 10000,
            "memberCount": 12,
            "cycleCount": 12,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    assert group_response.status_code == 201

    response = client.post(f"/api/groups/{group_response.json()['id']}/close-collection")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_group_status_returns_lifecycle_and_payment_counts(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "STATUS-001",
            "title": "Status Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    group_id = group_response.json()["id"]
    membership_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1},
    )
    membership_id = membership_response.json()["id"]
    installment = db_session.scalar(
        select(Installment).where(
            Installment.group_id == group_id,
            Installment.membership_id == membership_id,
            Installment.cycle_no == 1,
        )
    )
    assert installment is not None
    installment.status = "paid"
    installment.paid_amount = installment.due_amount
    installment.balance_amount = 0
    db_session.commit()

    response = client.get(f"/api/groups/{group_id}/status", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "collection_closed": False,
        "status": "OPEN",
        "paid_members": 1,
        "total_members": 1,
    }


def test_group_member_summary_returns_member_financials(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "MEM-SUM-001",
            "title": "Member Summary Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    group_id = group_response.json()["id"]
    membership_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1},
    )
    membership_id = membership_response.json()["id"]
    session = AuctionSession(
        group_id=group_id,
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
        membership_id=membership_id,
        bidder_user_id=1,
        idempotency_key="member-summary-bid",
        bid_amount=1000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 8, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()
    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group_id,
        cycle_no=1,
        winner_membership_id=membership_id,
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
                membership_id=membership_id,
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
                membership_id=membership_id,
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

    response = client.get(f"/api/groups/{group_id}/member-summary", headers=headers)

    assert response.status_code == 200
    assert response.json()[0]["paid"] == 1000
    assert response.json()[0]["received"] == 4000
    assert response.json()[0]["dividend"] == 100
    assert response.json()[0]["net"] == 3100


def test_create_membership_generates_installments(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "JUN-001",
            "title": "June Monthly Chit",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]

    response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1, "slotCount": 2},
    )
    assert response.status_code == 201
    assert response.json()["slotCount"] == 2
    assert response.json()["remainingSlotCount"] == 2
    membership = db_session.scalar(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    )
    slots = db_session.scalars(
        select(MembershipSlot).where(MembershipSlot.group_id == group_id).order_by(MembershipSlot.slot_number.asc())
    ).all()
    installments = db_session.scalars(
        select(Installment).where(Installment.group_id == group_id).order_by(Installment.cycle_no)
    ).all()
    assert membership is not None
    assert [slot.slot_number for slot in slots] == [1, 2]
    assert len(installments) == 5
    assert float(installments[0].due_amount) == 30000.0
    assert installments[0].cycle_no == 1


def test_create_membership_skips_elapsed_cycles_for_fresh_memberships(app, db_session, monkeypatch):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "JUN-LATE-001",
            "title": "Late Join Chit",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-01-01",
            "firstAuctionDate": "2026-01-10",
        },
    )
    group_id = group_response.json()["id"]
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    assert group is not None
    group.current_cycle_no = 2
    db_session.commit()

    monkeypatch.setattr(
        "app.modules.groups.service.utcnow",
        lambda: datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc),
    )

    response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1},
    )

    assert response.status_code == 201
    installments = db_session.scalars(
        select(Installment).where(Installment.group_id == group_id).order_by(Installment.cycle_no)
    ).all()
    assert [installment.cycle_no for installment in installments] == [3, 4, 5]
    assert [installment.due_date for installment in installments] == [
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
    ]


def test_create_auction_session_for_group(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-001",
            "title": "Auction Api Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={"cycleNo": 1, "biddingWindowSeconds": 240, "allowWithPending": True},
    )
    assert response.status_code == 201
    assert response.json()["groupId"] == group_id
    assert response.json()["auctionMode"] == "LIVE"
    assert response.json()["commissionMode"] == "NONE"
    assert response.json()["commissionValue"] is None
    assert response.json()["minBidValue"] == 0
    assert response.json()["maxBidValue"] == 300000
    assert response.json()["minIncrement"] == 1
    assert response.json()["status"] == "open"


def test_create_auction_session_requires_closed_collection(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-CLOSED-001",
            "title": "Auction Requires Closed Collection",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})

    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={"cycleNo": 1, "biddingWindowSeconds": 240},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Collection must be closed before starting an auction"


def test_create_auction_session_requires_collection_closed_lifecycle(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-LIFECYCLE-001",
            "title": "Auction Lifecycle Guard Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    assert group is not None
    group.current_month_status = "PAYOUT_DONE"
    group.collection_closed = True
    db_session.commit()

    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={"cycleNo": 1, "biddingWindowSeconds": 240, "allowWithPending": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Collection must be closed before starting an auction"


def test_create_auction_session_requires_pending_override(app):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-PENDING-001",
            "title": "Auction Pending Override Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)

    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={"cycleNo": 1, "biddingWindowSeconds": 240},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Pending payments exist for this cycle"


def test_create_auction_session_accepts_explicit_auction_mode(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-002",
            "title": "Auction Api Blind Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={
            "cycleNo": 1,
            "auctionMode": "BLIND",
            "allowWithPending": True,
            "commissionMode": "PERCENTAGE",
            "commissionValue": 5,
            "minBidValue": 1000,
            "maxBidValue": 25000,
            "minIncrement": 500,
            "biddingWindowSeconds": 240,
            "startTime": "2026-06-10T10:00:00Z",
            "endTime": "2026-06-10T10:04:00Z",
        },
    )

    assert response.status_code == 201
    assert response.json()["groupId"] == group_id
    assert response.json()["auctionMode"] == "BLIND"
    assert response.json()["commissionMode"] == "PERCENTAGE"
    assert response.json()["commissionValue"] == 5.0
    assert response.json()["minBidValue"] == 1000
    assert response.json()["maxBidValue"] == 25000
    assert response.json()["minIncrement"] == 500
    assert response.json()["status"] == "open"
    assert response.json()["startTime"].startswith("2026-06-10T10:00:00")
    assert response.json()["endTime"].startswith("2026-06-10T10:04:00")


def test_create_blind_auction_session_rejects_invalid_time_window(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-003",
            "title": "Auction Api Invalid Blind Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={
            "cycleNo": 1,
            "auctionMode": "BLIND",
            "allowWithPending": True,
            "biddingWindowSeconds": 240,
            "startTime": "2026-06-10T10:05:00Z",
            "endTime": "2026-06-10T10:04:00Z",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Blind auction endTime must be later than startTime"


def test_create_auction_session_rejects_invalid_commission_configuration(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-004",
            "title": "Auction Api Invalid Commission Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={
            "cycleNo": 1,
            "auctionMode": "LIVE",
            "allowWithPending": True,
            "commissionMode": "PERCENTAGE",
            "biddingWindowSeconds": 240,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Commission value is required for this commission mode"


def test_create_auction_session_rejects_invalid_bid_control_configuration(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-005",
            "title": "Auction Api Invalid Bid Control Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    client.post(f"/api/groups/{group_id}/memberships", headers=headers, json={"subscriberId": 1, "memberNo": 1})
    client.post(f"/api/groups/{group_id}/close-collection", headers=headers)
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=headers,
        json={
            "cycleNo": 1,
            "allowWithPending": True,
            "minBidValue": 5000,
            "maxBidValue": 4000,
            "minIncrement": 250,
            "biddingWindowSeconds": 240,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Maximum bid value must be greater than or equal to minimum bid value"


def test_record_payment_returns_recorded_status(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)
    response = client.post(
        "/api/payments",
        headers=headers,
        json={
            "ownerId": 1,
            "subscriberId": 2,
            "membershipId": None,
            "installmentId": None,
            "paymentType": "membership",
            "paymentMethod": "upi",
            "amount": 25000,
            "paymentDate": "2026-05-10",
            "referenceNo": "UPI-001",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "recorded"
    payment = db_session.scalar(select(Payment))
    assert payment is not None
    assert float(payment.amount) == 25000.0
