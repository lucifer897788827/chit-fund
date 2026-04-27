import json
import importlib
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models import AdminMessage, AuctionBid, AuctionResult, AuctionSession, ChitGroup, GroupMembership, Owner, Payment, Subscriber, User


def _admin_headers(client: TestClient, db_session) -> dict[str, str]:
    admin_user = User(
        email="admin-message@example.com",
        phone="7777777701",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()
    response = client.post("/api/auth/login", json={"phone": "7777777701", "password": "admin-secret"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_message_create_and_active_lookup(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    first_response = client.post(
        "/api/admin/messages",
        headers=headers,
        json={"message": "Collection window closes tonight", "type": "warning", "active": True},
    )
    second_response = client.post(
        "/api/admin/messages",
        headers=headers,
        json={"message": "System maintenance at 9 PM", "type": "critical", "active": True},
    )
    active_response = client.get("/api/admin/messages", headers=headers)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert active_response.status_code == 200
    assert active_response.json()["message"] == "System maintenance at 9 PM"
    assert active_response.json()["type"] == "critical"
    messages = db_session.query(AdminMessage).order_by(AdminMessage.id.asc()).all()
    assert [message.active for message in messages] == [False, True]


def test_active_admin_message_is_visible_to_authenticated_users(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    create_response = client.post(
        "/api/admin/messages",
        headers=headers,
        json={"message": "Collection window closes tonight", "type": "warning", "active": True},
    )
    assert create_response.status_code == 201

    login_response = client.post("/api/auth/login", json={"phone": "9999999999", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get("/api/admin/messages", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Collection window closes tonight"
    assert response.json()["type"] == "warning"


def test_admin_message_create_requires_admin(app):
    client = TestClient(app)
    login_response = client.post("/api/auth/login", json={"phone": "9999999999", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.post(
        "/api/admin/messages",
        headers=headers,
        json={"message": "Collection window closes tonight", "type": "warning", "active": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_message_create_requires_authentication(app):
    client = TestClient(app)

    response = client.post(
        "/api/admin/messages",
        json={"message": "Collection window closes tonight", "type": "warning", "active": True},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_admin_user_management_lists_and_reads_users(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    list_response = client.get("/api/admin/users?page=1&limit=20", headers=headers)
    detail_response = client.get("/api/admin/users/1", headers=headers)

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["page"] == 1
    assert list_body["pageSize"] == 20
    assert list_body["totalCount"] >= 1
    assert any(user["id"] == 1 and user["role"] == "owner" for user in list_body["items"])
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["id"] == 1
    assert body["role"] == "owner"
    assert "financialSummary" in body
    assert "participationStats" in body
    assert "chits" in body
    assert "payments" in body
    assert "externalChitsData" in body
    assert "paymentScore" in body["financialSummary"]


def test_admin_user_listing_emits_performance_breakdown(app, db_session, capsys):
    configure_logging(app_env="development", structured_logging=True, level="INFO")
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users", headers=headers)

    assert response.status_code == 200
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.strip().startswith("{")
    ]
    performance_log = next(
        payload for payload in payloads if payload.get("event") == "admin.performance"
    )
    assert performance_log["endpoint"] == "/api/admin/users"
    assert performance_log["user_id"] >= 1
    assert performance_log["db_query_ms"] >= 0
    assert performance_log["processing_ms"] >= 0
    assert performance_log["duration_ms"] >= 0


def test_admin_user_management_requires_admin(app):
    client = TestClient(app)
    login_response = client.post("/api/auth/login", json={"phone": "9999999999", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get("/api/admin/users", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_user_listing_paginates(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users?page=1&limit=1", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1


def test_admin_user_listing_uses_cache(app, db_session, monkeypatch):
    admin_service = importlib.import_module("app.modules.admin.service")
    cache_module = importlib.import_module("app.modules.admin.cache")
    store = {}

    class _FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value
            return True

    monkeypatch.setattr(cache_module, "redis_client", _FakeRedis())
    monkeypatch.setattr(admin_service, "load_admin_users_cache", cache_module.load_admin_users_cache)
    monkeypatch.setattr(admin_service, "store_admin_users_cache", cache_module.store_admin_users_cache)

    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    first_response = client.get("/api/admin/users?page=1&limit=20", headers=headers)

    def fail_count_statement(*args, **kwargs):
        raise AssertionError("cache miss unexpectedly hit count query")

    monkeypatch.setattr(admin_service, "count_statement", fail_count_statement)

    second_response = client.get("/api/admin/users?page=1&limit=20", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()


def test_admin_user_detail_lite_mode_keeps_contract(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users/1?lite=true", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert "financialSummary" in body
    assert "participationStats" in body
    assert body["financialSummary"]["paymentScore"] >= 0


def test_admin_user_management_returns_404_for_missing_user(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_admin_groups_endpoint_returns_group_summaries(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-GRP-1",
        title="Admin Review Group",
        chit_value=240000,
        installment_amount=12000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 1, 1),
        first_auction_date=date(2026, 1, 15),
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            GroupMembership(group_id=group.id, subscriber_id=1, member_no=1, membership_status="active", prized_status="unprized", can_bid=True),
            GroupMembership(group_id=group.id, subscriber_id=2, member_no=2, membership_status="active", prized_status="unprized", can_bid=True),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/groups", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(
        item["id"] == group.id
        and item["name"] == "Admin Review Group"
        and item["status"] == "active"
        and item["membersCount"] == 2
        and item["monthlyAmount"] == 12000
        for item in body
    )


def test_admin_auctions_endpoint_returns_auction_summaries(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-AUC-1",
        title="Auction Oversight Group",
        chit_value=300000,
        installment_amount=15000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 2, 1),
        first_auction_date=date(2026, 2, 15),
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
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
        scheduled_start_at=datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc),
        status="closed",
    )
    db_session.add(session)
    db_session.flush()
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=2,
        idempotency_key="admin-auction-bid",
        bid_amount=45000,
        bid_discount_amount=45000,
    )
    db_session.add(bid)
    db_session.flush()
    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=1,
        winner_membership_id=membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=45000,
        dividend_pool_amount=0,
        dividend_per_member_amount=0,
        owner_commission_amount=0,
        winner_payout_amount=255000,
        finalized_by_user_id=1,
    )
    db_session.add(result)
    db_session.commit()

    response = client.get("/api/admin/auctions", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(
        item["id"] == session.id
        and item["group"] == "Auction Oversight Group"
        and item["winner"] == "Subscriber One"
        and item["bidAmount"] == 45000
        and item["status"] == "closed"
        for item in body
    )


def test_admin_payments_endpoint_returns_payment_summaries(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-PAY-1",
        title="Payment Oversight Group",
        chit_value=180000,
        installment_amount=9000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 3, 1),
        first_auction_date=date(2026, 3, 15),
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    payment = Payment(
        owner_id=owner.id,
        subscriber_id=2,
        membership_id=membership.id,
        installment_id=None,
        payment_type="installment",
        payment_method="cash",
        amount=9000,
        payment_date=date(2026, 3, 5),
        recorded_by_user_id=1,
        status="recorded",
    )
    db_session.add(payment)
    db_session.commit()

    response = client.get("/api/admin/payments", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(
        item["id"] == payment.id
        and item["user"] == "Subscriber One"
        and item["group"] == "Payment Oversight Group"
        and item["amount"] == 9000
        and item["status"] == "paid"
        for item in body
    )
