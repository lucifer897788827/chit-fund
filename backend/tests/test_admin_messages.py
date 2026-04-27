import json
import importlib

from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models import AdminMessage, User


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
