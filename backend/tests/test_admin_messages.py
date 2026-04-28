import json
import importlib
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models import AdminMessage, AuctionBid, AuctionResult, AuctionSession, ChitGroup, GroupMembership, Installment, Owner, Payment, Payout, Subscriber, User


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
    assert "netPosition" in body["financialSummary"]


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


def test_admin_user_listing_filters_by_role_and_active_state(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    inactive_user = User(
        email="inactive-owner@example.com",
        phone="7777777710",
        password_hash=hash_password("owner-secret"),
        role="chit_owner",
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.flush()
    db_session.add(
        Owner(
            user_id=inactive_user.id,
            display_name="Inactive Owner",
            business_name="Inactive Owner Chits",
            city="Chennai",
            state="TN",
            status="inactive",
        )
    )
    db_session.commit()

    response = client.get("/api/admin/users?role=owner&active=false", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["totalCount"] >= 1
    assert all(item["role"] == "owner" and item["isActive"] is False for item in body["items"])
    assert any(item["name"] == "Inactive Owner" for item in body["items"])


def test_admin_user_listing_searches_phone_and_name(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users?search=subscriber%20one", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["totalCount"] >= 1
    assert any(item["phone"] == "9999999999" or item["name"] == "Subscriber One" for item in body["items"])


def test_admin_user_listing_filters_by_payment_score_range(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    assert owner is not None

    user = User(
        email="score-user@example.com",
        phone="7777777735",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner.id,
        full_name="Score User",
        phone=user.phone,
        email=user.email,
        status="active",
        auto_created=False,
    )
    db_session.add(subscriber)
    db_session.flush()
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-SCORE-1",
        title="Score Filter Group",
        chit_value=120000,
        installment_amount=6000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=7,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 5),
                due_amount=6000,
                penalty_amount=0,
                paid_amount=6000,
                balance_amount=0,
                status="paid",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 4, 10),
                due_amount=6000,
                penalty_amount=0,
                paid_amount=6000,
                balance_amount=0,
                status="paid",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=3,
                due_date=date(2026, 4, 15),
                due_amount=6000,
                penalty_amount=0,
                paid_amount=6000,
                balance_amount=0,
                status="paid",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=4,
                due_date=date(2026, 4, 20),
                due_amount=6000,
                penalty_amount=0,
                paid_amount=6000,
                balance_amount=0,
                status="paid",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=5,
                due_date=date(2026, 4, 25),
                due_amount=6000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=6000,
                status="pending",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/users?scoreRange=high&search=score%20user", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["totalCount"] == 1
    assert body["items"][0]["phone"] == "7777777735"
    assert body["items"][0]["paymentScore"] == 80


def test_admin_group_detail_returns_summary_members_financials_auctions_and_defaulters(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    admin_user = db_session.scalar(select(User).where(User.phone == "7777777701"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    assert admin_user is not None
    assert owner is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-GRP-1",
        title="Admin Detail Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        current_cycle_no=2,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    first_user = User(
        email="group-member-one@example.com",
        phone="7777777741",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    second_user = User(
        email="group-member-two@example.com",
        phone="7777777742",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add_all([first_user, second_user])
    db_session.flush()
    first_subscriber = Subscriber(
        user_id=first_user.id,
        owner_id=owner.id,
        full_name="Group Member One",
        phone=first_user.phone,
        email=first_user.email,
        status="active",
        auto_created=False,
    )
    second_subscriber = Subscriber(
        user_id=second_user.id,
        owner_id=owner.id,
        full_name="Group Member Two",
        phone=second_user.phone,
        email=second_user.email,
        status="active",
        auto_created=False,
    )
    db_session.add_all([first_subscriber, second_subscriber])
    db_session.flush()
    first_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=first_subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    second_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=second_subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="prized",
        can_bid=True,
    )
    db_session.add_all([first_membership, second_membership])
    db_session.flush()

    paid_installment = Installment(
        group_id=group.id,
        membership_id=first_membership.id,
        cycle_no=1,
        due_date=date(2026, 4, 5),
        due_amount=10000,
        penalty_amount=0,
        paid_amount=10000,
        balance_amount=0,
        status="paid",
    )
    pending_installment_one = Installment(
        group_id=group.id,
        membership_id=first_membership.id,
        cycle_no=2,
        due_date=date(2026, 5, 5),
        due_amount=10000,
        penalty_amount=0,
        paid_amount=0,
        balance_amount=6000,
        status="pending",
    )
    pending_installment_two = Installment(
        group_id=group.id,
        membership_id=first_membership.id,
        cycle_no=3,
        due_date=date(2026, 6, 5),
        due_amount=10000,
        penalty_amount=0,
        paid_amount=0,
        balance_amount=4000,
        status="partial",
    )
    second_paid_installment = Installment(
        group_id=group.id,
        membership_id=second_membership.id,
        cycle_no=1,
        due_date=date(2026, 4, 5),
        due_amount=10000,
        penalty_amount=0,
        paid_amount=10000,
        balance_amount=0,
        status="paid",
    )
    db_session.add_all([paid_installment, pending_installment_one, pending_installment_two, second_paid_installment])
    db_session.flush()

    payment = Payment(
        owner_id=owner.id,
        subscriber_id=first_subscriber.id,
        membership_id=first_membership.id,
        installment_id=paid_installment.id,
        payment_type="installment",
        payment_method="upi",
        amount=10000,
        payment_date=date(2026, 4, 5),
        recorded_by_user_id=admin_user.id,
        status="paid",
    )
    db_session.add(payment)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        status="closed",
    )
    db_session.add(session)
    db_session.flush()
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=second_membership.id,
        bidder_user_id=second_user.id,
        idempotency_key="group-detail-bid",
        bid_amount=15000,
        bid_discount_amount=15000,
        placed_at=datetime(2026, 4, 15, 10, 15, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()
    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=1,
        winner_membership_id=second_membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=15000,
        dividend_pool_amount=2000,
        dividend_per_member_amount=1000,
        owner_commission_amount=500,
        winner_payout_amount=8500,
        finalized_by_user_id=admin_user.id,
    )
    db_session.add(result)
    db_session.flush()
    payout = Payout(
        owner_id=owner.id,
        auction_result_id=result.id,
        subscriber_id=second_subscriber.id,
        membership_id=second_membership.id,
        gross_amount=10000,
        deductions_amount=1500,
        net_amount=8500,
        payout_method="bank_transfer",
        payout_date=date(2026, 4, 16),
        status="paid",
    )
    db_session.add(payout)
    db_session.commit()

    response = client.get(f"/api/admin/groups/{group.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["group"]["name"] == "Admin Detail Group"
    assert body["group"]["membersCount"] == 2
    assert body["financialSummary"] == {
        "totalCollected": 10000,
        "totalPaid": 8500,
        "pendingAmount": 10000,
    }
    assert len(body["members"]) == 2
    first_member = next(item for item in body["members"] if item["phone"] == "7777777741")
    assert first_member["totalPaid"] == 10000
    assert first_member["totalReceived"] == 0
    assert first_member["netPosition"] == -10000
    assert first_member["paymentScore"] == 33
    assert first_member["pendingPaymentsCount"] == 2
    assert len(body["auctions"]) == 1
    assert body["auctions"][0]["winner"] == "Group Member Two"
    assert body["auctions"][0]["bidAmount"] == 15000
    assert body["defaulters"] == [
        {
            "userId": first_user.id,
            "name": "Group Member One",
            "phone": "7777777741",
            "pendingPaymentsCount": 2,
            "pendingAmount": 10000,
            "paymentScore": 33,
            "netPosition": -10000,
        }
    ]


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
    assert "netPosition" in body["financialSummary"]


def test_admin_user_management_returns_404_for_missing_user(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/admin/users/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_admin_user_deactivation_marks_user_and_profiles_inactive(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner_user = User(
        email="deactivate-owner@example.com",
        phone="7777777720",
        password_hash=hash_password("owner-secret"),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_user)
    db_session.flush()
    owner = Owner(
        user_id=owner_user.id,
        display_name="Deactivate Owner",
        business_name="Deactivate Owner Chits",
        city="Madurai",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.flush()
    subscriber = Subscriber(
        user_id=owner_user.id,
        owner_id=owner.id,
        full_name="Deactivate Owner",
        phone=owner_user.phone,
        email=owner_user.email,
        status="active",
        auto_created=False,
    )
    db_session.add(subscriber)
    db_session.commit()

    response = client.post(f"/api/admin/users/{owner_user.id}/deactivate", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"id": owner_user.id, "isActive": False}
    db_session.refresh(owner_user)
    db_session.refresh(owner)
    db_session.refresh(subscriber)
    assert owner_user.is_active is False
    assert owner.status == "inactive"
    assert subscriber.status == "inactive"


def test_admin_user_bulk_deactivation_soft_disables_multiple_users(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    first_user = User(
        email="bulk-user-1@example.com",
        phone="7777777721",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    second_user = User(
        email="bulk-user-2@example.com",
        phone="7777777722",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add_all([first_user, second_user])
    db_session.flush()
    db_session.add_all(
        [
            Subscriber(
                user_id=first_user.id,
                owner_id=1,
                full_name="Bulk User One",
                phone=first_user.phone,
                email=first_user.email,
                status="active",
                auto_created=False,
            ),
            Subscriber(
                user_id=second_user.id,
                owner_id=1,
                full_name="Bulk User Two",
                phone=second_user.phone,
                email=second_user.email,
                status="active",
                auto_created=False,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/admin/users/bulk-deactivate",
        headers=headers,
        json={"userIds": [first_user.id, second_user.id]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deactivatedUserIds": [first_user.id, second_user.id],
        "count": 2,
    }
    db_session.refresh(first_user)
    db_session.refresh(second_user)
    assert first_user.is_active is False
    assert second_user.is_active is False


def test_admin_user_activation_marks_user_and_profiles_active(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner_user = User(
        email="activate-owner@example.com",
        phone="7777777724",
        password_hash=hash_password("owner-secret"),
        role="chit_owner",
        is_active=False,
    )
    db_session.add(owner_user)
    db_session.flush()
    owner = Owner(
        user_id=owner_user.id,
        display_name="Activate Owner",
        business_name="Activate Owner Chits",
        city="Coimbatore",
        state="Tamil Nadu",
        status="inactive",
    )
    db_session.add(owner)
    db_session.flush()
    subscriber = Subscriber(
        user_id=owner_user.id,
        owner_id=owner.id,
        full_name="Activate Owner",
        phone=owner_user.phone,
        email=owner_user.email,
        status="inactive",
        auto_created=False,
    )
    db_session.add(subscriber)
    db_session.commit()

    response = client.post(f"/api/admin/users/{owner_user.id}/activate", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"id": owner_user.id, "isActive": True}
    db_session.refresh(owner_user)
    db_session.refresh(owner)
    db_session.refresh(subscriber)
    assert owner_user.is_active is True
    assert owner.status == "active"
    assert subscriber.status == "active"


def test_admin_user_deactivation_blocks_admin_targets(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    second_admin = User(
        email="other-admin@example.com",
        phone="7777777723",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=True,
    )
    db_session.add(second_admin)
    db_session.commit()

    response = client.post(f"/api/admin/users/{second_admin.id}/deactivate", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Admin users cannot be deactivated"
    db_session.refresh(second_admin)
    assert second_admin.is_active is True


def test_admin_user_activation_blocks_admin_targets(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    second_admin = User(
        email="other-admin-activate@example.com",
        phone="7777777725",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=False,
    )
    db_session.add(second_admin)
    db_session.commit()

    response = client.post(f"/api/admin/users/{second_admin.id}/activate", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Admin users cannot be activated"
    db_session.refresh(second_admin)
    assert second_admin.is_active is False


def test_admin_user_deactivation_blocks_self_deactivation(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    admin_user = db_session.scalar(select(User).where(User.phone == "7777777701"))
    assert admin_user is not None

    response = client.post(f"/api/admin/users/{admin_user.id}/deactivate", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Admins cannot deactivate themselves"
    db_session.refresh(admin_user)
    assert admin_user.is_active is True


def test_admin_user_activation_blocks_self_activation(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    admin_user = db_session.scalar(select(User).where(User.phone == "7777777701"))
    assert admin_user is not None

    response = client.post(f"/api/admin/users/{admin_user.id}/activate", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Admins cannot activate themselves"
    db_session.refresh(admin_user)
    assert admin_user.is_active is True


def test_admin_defaulters_endpoint_returns_high_risk_users_above_threshold(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    assert owner is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-DEF-1",
        title="Admin Defaulters Group",
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

    risky_user = User(
        email="defaulter-one@example.com",
        phone="7777777730",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    safe_user = User(
        email="defaulter-two@example.com",
        phone="7777777731",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add_all([risky_user, safe_user])
    db_session.flush()

    risky_subscriber = Subscriber(
        user_id=risky_user.id,
        owner_id=owner.id,
        full_name="Risky Subscriber",
        phone=risky_user.phone,
        email=risky_user.email,
        status="active",
        auto_created=False,
    )
    safe_subscriber = Subscriber(
        user_id=safe_user.id,
        owner_id=owner.id,
        full_name="Safe Subscriber",
        phone=safe_user.phone,
        email=safe_user.email,
        status="active",
        auto_created=False,
    )
    db_session.add_all([risky_subscriber, safe_subscriber])
    db_session.flush()

    risky_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=risky_subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    safe_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=safe_subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([risky_membership, safe_membership])
    db_session.flush()

    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=risky_membership.id,
                cycle_no=1,
                due_date=date(2026, 1, 5),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=12000,
                status="pending",
            ),
            Installment(
                group_id=group.id,
                membership_id=risky_membership.id,
                cycle_no=2,
                due_date=date(2026, 2, 5),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=4000,
                balance_amount=8000,
                status="partial",
            ),
            Installment(
                group_id=group.id,
                membership_id=safe_membership.id,
                cycle_no=1,
                due_date=date(2026, 1, 5),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=12000,
                status="pending",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/insights/defaulters?threshold=1", headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "userId": risky_user.id,
            "name": "Risky Subscriber",
            "phone": "7777777730",
            "pendingPaymentsCount": 2,
            "pendingAmount": 20000,
        }
    ]


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


def test_admin_groups_endpoint_filters_by_status(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    active_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-GRP-ACT",
        title="Active Admin Group",
        chit_value=240000,
        installment_amount=12000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 1, 1),
        first_auction_date=date(2026, 1, 15),
        status="active",
    )
    completed_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-GRP-CMP",
        title="Completed Admin Group",
        chit_value=240000,
        installment_amount=12000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 1, 1),
        first_auction_date=date(2026, 1, 15),
        status="completed",
    )
    db_session.add_all([active_group, completed_group])
    db_session.commit()

    response = client.get("/api/admin/groups?status=completed", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(item["name"] == "Completed Admin Group" for item in body)
    assert all(item["status"] == "completed" for item in body)


def test_admin_groups_endpoint_searches_group_and_owner_name(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-GRP-SRCH",
        title="Searchable Admin Group",
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
    db_session.commit()

    response = client.get("/api/admin/groups?search=searchable", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(item["name"] == "Searchable Admin Group" for item in body)


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
        and item["scheduledAt"].startswith("2026-02-15")
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
        and item["groupId"] == group.id
        and item["amount"] == 9000
        and item["status"] == "paid"
        for item in body
    )


def test_admin_payments_endpoint_filters_by_status(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-PAY-FLT",
        title="Filtered Payment Group",
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
    db_session.add_all(
        [
            Payment(
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
            ),
            Payment(
                owner_id=owner.id,
                subscriber_id=2,
                membership_id=membership.id,
                installment_id=None,
                payment_type="installment",
                payment_method="cash",
                amount=9000,
                payment_date=date(2026, 3, 6),
                recorded_by_user_id=1,
                status="pending",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/payments?status=pending", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert all(item["status"] == "pending" for item in body)


def test_admin_payments_endpoint_searches_phone_and_name(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-PAY-SRCH",
        title="Search Payment Group",
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
    db_session.add(
        Payment(
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
    )
    db_session.commit()

    response = client.get("/api/admin/payments?search=subscriber%20one", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(item["user"] == "Subscriber One" for item in body)


def test_admin_defaulters_endpoint_returns_users_above_threshold_sorted_by_risk(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))

    first_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-DFT-1",
        title="Defaulter Group One",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="active",
    )
    second_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-DFT-2",
        title="Defaulter Group Two",
        chit_value=240000,
        installment_amount=12000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="active",
    )
    db_session.add_all([first_group, second_group])
    db_session.flush()

    high_risk_user = User(
        email="high-risk@example.com",
        phone="7777777730",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    medium_risk_user = User(
        email="medium-risk@example.com",
        phone="7777777731",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    below_threshold_user = User(
        email="below-threshold@example.com",
        phone="7777777732",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add_all([high_risk_user, medium_risk_user, below_threshold_user])
    db_session.flush()

    high_risk_subscriber = Subscriber(
        user_id=high_risk_user.id,
        owner_id=owner.id,
        full_name="High Risk User",
        phone=high_risk_user.phone,
        email=high_risk_user.email,
        status="active",
        auto_created=False,
    )
    medium_risk_subscriber = Subscriber(
        user_id=medium_risk_user.id,
        owner_id=owner.id,
        full_name="Medium Risk User",
        phone=medium_risk_user.phone,
        email=medium_risk_user.email,
        status="active",
        auto_created=False,
    )
    below_threshold_subscriber = Subscriber(
        user_id=below_threshold_user.id,
        owner_id=owner.id,
        full_name="Below Threshold User",
        phone=below_threshold_user.phone,
        email=below_threshold_user.email,
        status="active",
        auto_created=False,
    )
    db_session.add_all([high_risk_subscriber, medium_risk_subscriber, below_threshold_subscriber])
    db_session.flush()

    high_risk_membership = GroupMembership(
        group_id=first_group.id,
        subscriber_id=high_risk_subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    medium_risk_membership = GroupMembership(
        group_id=second_group.id,
        subscriber_id=medium_risk_subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    below_threshold_membership = GroupMembership(
        group_id=second_group.id,
        subscriber_id=below_threshold_subscriber.id,
        member_no=3,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([high_risk_membership, medium_risk_membership, below_threshold_membership])
    db_session.flush()

    db_session.add_all(
        [
            Installment(
                group_id=first_group.id,
                membership_id=high_risk_membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 5),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=1000,
                balance_amount=9000,
                status="pending",
            ),
            Installment(
                group_id=first_group.id,
                membership_id=high_risk_membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 5),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=10000,
                status="due",
            ),
            Installment(
                group_id=first_group.id,
                membership_id=high_risk_membership.id,
                cycle_no=3,
                due_date=date(2026, 6, 5),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=8000,
                status="partial",
            ),
            Installment(
                group_id=second_group.id,
                membership_id=medium_risk_membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 10),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=3000,
                balance_amount=9000,
                status="pending",
            ),
            Installment(
                group_id=second_group.id,
                membership_id=medium_risk_membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 10),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=9000,
                status="partial",
            ),
            Installment(
                group_id=second_group.id,
                membership_id=below_threshold_membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 12),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=6000,
                balance_amount=6000,
                status="pending",
            ),
            Installment(
                group_id=second_group.id,
                membership_id=below_threshold_membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 12),
                due_amount=12000,
                penalty_amount=0,
                paid_amount=12000,
                balance_amount=0,
                status="paid",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/insights/defaulters", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "userId": high_risk_user.id,
            "name": "High Risk User",
            "phone": "7777777730",
            "pendingPaymentsCount": 3,
            "pendingAmount": 27000,
        },
        {
            "userId": medium_risk_user.id,
            "name": "Medium Risk User",
            "phone": "7777777731",
            "pendingPaymentsCount": 2,
            "pendingAmount": 18000,
        },
    ]


def test_admin_defaulters_endpoint_respects_threshold_query_param(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    user = User(
        email="threshold-user@example.com",
        phone="7777777733",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner.id,
        full_name="Threshold User",
        phone=user.phone,
        email=user.email,
        status="active",
        auto_created=False,
    )
    db_session.add(subscriber)
    db_session.flush()
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-DFT-TH",
        title="Threshold Group",
        chit_value=180000,
        installment_amount=9000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
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
    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 8),
                due_amount=9000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=4500,
                status="pending",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 8),
                due_amount=9000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=4500,
                status="partial",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/insights/defaulters?threshold=2", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


def test_admin_insights_summary_endpoint_returns_dashboard_counts(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    baseline_response = client.get("/api/admin/insights/summary", headers=headers)
    assert baseline_response.status_code == 200
    baseline = baseline_response.json()

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    assert owner is not None

    active_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-SUM-ACT",
        title="Active Summary Group",
        chit_value=180000,
        installment_amount=9000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="active",
    )
    completed_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-SUM-CMP",
        title="Completed Summary Group",
        chit_value=180000,
        installment_amount=9000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="completed",
    )
    db_session.add_all([active_group, completed_group])
    db_session.flush()

    defaulter_user = User(
        email="summary-defaulter@example.com",
        phone="7777777740",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add(defaulter_user)
    db_session.flush()

    defaulter_subscriber = Subscriber(
        user_id=defaulter_user.id,
        owner_id=owner.id,
        full_name="Summary Defaulter",
        phone=defaulter_user.phone,
        email=defaulter_user.email,
        status="active",
        auto_created=False,
    )
    db_session.add(defaulter_subscriber)
    db_session.flush()

    membership = GroupMembership(
        group_id=active_group.id,
        subscriber_id=defaulter_subscriber.id,
        member_no=5,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    db_session.add_all(
        [
            Payment(
                owner_id=owner.id,
                subscriber_id=defaulter_subscriber.id,
                membership_id=membership.id,
                installment_id=None,
                payment_type="installment",
                payment_method="cash",
                amount=9000,
                payment_date=date(2026, 4, 5),
                recorded_by_user_id=1,
                status="pending",
            ),
            Payment(
                owner_id=owner.id,
                subscriber_id=defaulter_subscriber.id,
                membership_id=membership.id,
                installment_id=None,
                payment_type="installment",
                payment_method="cash",
                amount=9000,
                payment_date=date(2026, 4, 6),
                recorded_by_user_id=1,
                status="recorded",
            ),
            Installment(
                group_id=active_group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 8),
                due_amount=9000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=4500,
                status="pending",
            ),
            Installment(
                group_id=active_group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 8),
                due_amount=9000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=4500,
                status="partial",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/insights/summary", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "totalUsers": baseline["totalUsers"] + 1,
        "activeGroups": baseline["activeGroups"] + 1,
        "pendingPayments": baseline["pendingPayments"] + 1,
        "defaulters": baseline["defaulters"] + 1,
    }


def test_admin_insights_summary_endpoint_requires_admin(app):
    client = TestClient(app)
    login_response = client.post("/api/auth/login", json={"phone": "9999999999", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get("/api/admin/insights/summary", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_insights_summary_endpoint_returns_dashboard_counts(app, db_session):
    client = TestClient(app)
    headers = _admin_headers(client, db_session)
    admin_user = db_session.scalar(select(User).where(User.phone == "7777777701"))
    assert admin_user is not None
    baseline = client.get("/api/admin/insights/summary", headers=headers)
    assert baseline.status_code == 200
    baseline_body = baseline.json()

    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    assert owner is not None

    user = User(
        email="summary-user@example.com",
        phone="7777777734",
        password_hash=hash_password("subscriber-secret"),
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner.id,
        full_name="Summary User",
        phone=user.phone,
        email=user.email,
        status="active",
        auto_created=False,
    )
    db_session.add(subscriber)
    db_session.flush()
    active_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-SUM-1",
        title="Summary Active Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 15),
        status="active",
    )
    completed_group = ChitGroup(
        owner_id=owner.id,
        group_code="ADM-SUM-2",
        title="Summary Completed Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 1, 1),
        first_auction_date=date(2026, 1, 15),
        status="completed",
    )
    db_session.add_all([active_group, completed_group])
    db_session.flush()
    membership = GroupMembership(
        group_id=active_group.id,
        subscriber_id=subscriber.id,
        member_no=5,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    db_session.add_all(
        [
                Payment(
                    owner_id=owner.id,
                    subscriber_id=subscriber.id,
                    membership_id=membership.id,
                    recorded_by_user_id=admin_user.id,
                    amount=5000,
                    payment_date=date(2026, 4, 8),
                    status="pending",
                    payment_type="installment",
                    payment_method="upi",
                ),
                Payment(
                    owner_id=owner.id,
                    subscriber_id=subscriber.id,
                    membership_id=membership.id,
                    recorded_by_user_id=admin_user.id,
                    amount=5000,
                    payment_date=date(2026, 5, 8),
                    status="due",
                    payment_type="installment",
                    payment_method="cash",
                ),
                Payment(
                    owner_id=owner.id,
                    subscriber_id=subscriber.id,
                    membership_id=membership.id,
                    recorded_by_user_id=admin_user.id,
                    amount=5000,
                    payment_date=date(2026, 5, 10),
                    status="paid",
                payment_type="installment",
                payment_method="cash",
            ),
            Installment(
                group_id=active_group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 8),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=5000,
                status="pending",
            ),
            Installment(
                group_id=active_group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 5, 8),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=5000,
                status="partial",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/admin/insights/summary", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "totalUsers": baseline_body["totalUsers"] + 1,
        "activeGroups": baseline_body["activeGroups"] + 1,
        "pendingPayments": baseline_body["pendingPayments"] + 2,
        "defaulters": baseline_body["defaulters"] + 1,
    }
