from datetime import datetime, timedelta, timezone
import json

import pytest
from jose import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password, hash_password_reset_token, verify_password
from app.core.time import utcnow
from app.models.auth import RefreshToken
from app.models.user import Owner, Subscriber, User
from app.modules.auth import service as auth_service


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}
        self.deleted_keys: list[tuple[str, ...]] = []

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value, ex=None):
        self.values[key] = int(value) if value is not None else value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def delete(self, *keys: str) -> int:
        self.deleted_keys.append(keys)
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
            self.expirations.pop(key, None)
        return deleted


@pytest.fixture(autouse=True)
def fake_auth_redis(monkeypatch):
    backend = FakeRedis()
    monkeypatch.setattr(auth_service, "redis_client", backend, raising=False)
    yield backend


def test_health_route_exists(app):
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_returns_access_token(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["refresh_token_expires_at"] is not None
    assert body["access_token_expires_in"] == 900
    assert body["refresh_token_expires_in"] == 2592000
    assert body["role"] == "chit_owner"
    assert body["roles"] == ["subscriber", "owner"]
    assert body["owner_id"] == 1
    assert body["has_subscriber_profile"] is True
    assert body["user"] == {"id": 1, "roles": ["subscriber", "owner"]}
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "1"
    assert claims["typ"] == "access"


def test_login_emits_performance_breakdown(app, capsys, monkeypatch):
    configure_logging(app_env="development", structured_logging=True, level="INFO")
    ticks = iter([10.0 + (index * 0.01) for index in range(40)])
    monkeypatch.setattr(
        auth_service,
        "perf_counter",
        ticks.__next__,
        raising=False,
    )

    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )

    assert response.status_code == 200
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.strip().startswith("{")
    ]
    performance_log = next(payload for payload in payloads if payload.get("event") == "auth.login.performance")
    assert performance_log["db_fetch_ms"] >= 0
    assert performance_log["hash_verify_ms"] >= 0
    assert performance_log["jwt_ms"] >= 0
    assert performance_log["total_ms"] >= 0
    assert performance_log["success"] is True


def test_login_updates_last_login_timestamp(app, db_session):
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    assert user is not None
    assert user.last_login_at is None

    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )

    assert response.status_code == 200

    db_session.refresh(user)
    assert user.last_login_at is not None


def test_refresh_rotates_refresh_token(app, db_session):
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    original_refresh_token = login_body["refresh_token"]

    db_session.add_all(
        [
            RefreshToken(
                user_id=1,
                token_hash="stale-revoked-token",
                expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                revoked_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            RefreshToken(
                user_id=1,
                token_hash="stale-expired-token",
                expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                revoked_at=None,
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": original_refresh_token},
    )
    assert refresh_response.status_code == 200
    refresh_body = refresh_response.json()

    assert refresh_body["access_token"] != login_body["access_token"]
    assert refresh_body["refresh_token"] != original_refresh_token
    assert refresh_body["role"] == "chit_owner"
    assert refresh_body["roles"] == ["subscriber", "owner"]
    assert refresh_body["user"] == {"id": 1, "roles": ["subscriber", "owner"]}

    rejected = client.post(
        "/api/auth/refresh",
        json={"refresh_token": original_refresh_token},
    )
    assert rejected.status_code == 401

    tokens = db_session.scalars(
        select(RefreshToken).where(RefreshToken.user_id == 1).order_by(RefreshToken.id)
    ).all()
    assert len(tokens) == 2
    assert tokens[0].revoked_at is not None
    assert tokens[1].revoked_at is None
    assert db_session.scalar(select(RefreshToken).where(RefreshToken.token_hash == "stale-revoked-token")) is None
    assert db_session.scalar(select(RefreshToken).where(RefreshToken.token_hash == "stale-expired-token")) is None


def test_logout_revokes_current_refresh_token(app, db_session):
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    headers = {"Authorization": f"Bearer {login_body['access_token']}"}

    dashboard_response = client.get("/api/reporting/owner/dashboard", headers=headers)
    assert dashboard_response.status_code == 200

    logout_response = client.post(
        "/api/auth/logout",
        json={"refresh_token": login_body["refresh_token"]},
        headers=headers,
    )
    assert logout_response.status_code == 204

    rejected_refresh = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
    )
    assert rejected_refresh.status_code == 401

    token = db_session.scalar(
        select(RefreshToken).where(RefreshToken.user_id == 1).order_by(RefreshToken.id.desc())
    )
    assert token is not None
    assert token.revoked_at is not None


def test_refresh_and_logout_accept_camel_case_refresh_token_payloads(app):
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200
    original_refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refreshToken": original_refresh_token},
    )
    assert refresh_response.status_code == 200
    headers = {"Authorization": f"Bearer {refresh_response.json()['access_token']}"}

    logout_response = client.post(
        "/api/auth/logout",
        json={"refreshToken": refresh_response.json()["refresh_token"]},
        headers=headers,
    )
    assert logout_response.status_code == 204


def test_logout_requires_authenticated_session(app):
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200

    logout_response = client.post(
        "/api/auth/logout",
        json={"refreshToken": login_response.json()["refresh_token"]},
    )

    assert logout_response.status_code == 401


def test_login_rejects_invalid_password(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_missing_user_exits_before_password_verification(app, monkeypatch):
    def fail_verify_password(*_args, **_kwargs):
        raise AssertionError("Password verification should not run for a missing user")

    monkeypatch.setattr(auth_service, "verify_password", fail_verify_password)

    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "0000000000", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_password_reset_request_returns_token_and_persists_hash(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "development"
    client = TestClient(app)
    try:
        response = client.post("/api/auth/request-reset", json={"phone": "9999999999"})

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "If an account exists, a password reset token has been generated."
        assert body["reset_token"]

        user = db_session.scalar(select(User).where(User.phone == "9999999999"))
        assert user is not None
        assert user.password_reset_token_hash == hash_password_reset_token(body["reset_token"])
        assert user.password_reset_token_expires_at is not None
    finally:
        settings.app_env = original_app_env


def test_password_reset_request_hides_token_in_production(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "production"
    client = TestClient(app)
    try:
        response = client.post("/api/auth/request-reset", json={"phone": "9999999999"})

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "If an account exists, a password reset token has been generated."
        assert body["reset_token"] is None
        assert body["reset_token_expires_at"] is None

        user = db_session.scalar(select(User).where(User.phone == "9999999999"))
        assert user is not None
        assert user.password_reset_token_hash is not None
        assert user.password_reset_token_expires_at is not None
    finally:
        settings.app_env = original_app_env


def test_password_reset_confirm_updates_password_and_blocks_reuse(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "development"
    client = TestClient(app)
    try:
        login_response = client.post(
            "/api/auth/login",
            json={"phone": "9999999999", "password": "secret123"},
        )
        assert login_response.status_code == 200
        issued_refresh_token = login_response.json()["refresh_token"]

        second_login_response = client.post(
            "/api/auth/login",
            json={"phone": "9999999999", "password": "secret123"},
        )
        assert second_login_response.status_code == 200

        request_response = client.post("/api/auth/request-reset", json={"phone": "9999999999"})
        token = request_response.json()["reset_token"]

        response = client.post(
            "/api/auth/confirm-reset",
            json={"token": token, "new_password": "reset-secret-123"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Password has been reset"

        user = db_session.scalar(select(User).where(User.phone == "9999999999"))
        assert user is not None
        assert user.password_reset_token_hash is None
        assert user.password_reset_token_expires_at is None
        assert verify_password("reset-secret-123", user.password_hash)

        tokens = db_session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == 1).order_by(RefreshToken.id)
        ).all()
        assert len(tokens) == 2
        assert all(token.revoked_at is not None for token in tokens)

        refresh_reuse_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": issued_refresh_token},
        )
        assert refresh_reuse_response.status_code == 401

        login_response = client.post(
            "/api/auth/login",
            json={"phone": "9999999999", "password": "reset-secret-123"},
        )
        assert login_response.status_code == 200

        reuse_response = client.post(
            "/api/auth/confirm-reset",
            json={"token": token, "new_password": "another-secret-123"},
        )
        assert reuse_response.status_code == 400
        assert reuse_response.json()["detail"] == "Invalid or expired password reset token"
    finally:
        settings.app_env = original_app_env


def test_password_reset_token_expiry_rejects_confirmation(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "development"
    client = TestClient(app)
    try:
        request_response = client.post("/api/auth/request-reset", json={"phone": "9999999999"})
        token = request_response.json()["reset_token"]

        user = db_session.scalar(select(User).where(User.phone == "9999999999"))
        assert user is not None
        user.password_reset_token_expires_at = utcnow() - timedelta(minutes=1)
        db_session.commit()

        response = client.post(
            "/api/auth/confirm-reset",
            json={"token": token, "new_password": "expired-secret-123"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired password reset token"

        login_response = client.post(
            "/api/auth/login",
            json={"phone": "9999999999", "password": "secret123"},
        )
        assert login_response.status_code == 200
    finally:
        settings.app_env = original_app_env


def test_password_reset_confirm_rejects_short_password(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "development"
    client = TestClient(app)
    try:
        request_response = client.post("/api/auth/request-reset", json={"phone": "9999999999"})
        token = request_response.json()["reset_token"]

        response = client.post(
            "/api/auth/confirm-reset",
            json={"token": token, "new_password": "short"},
        )

        assert response.status_code == 422

        old_login_response = client.post(
            "/api/auth/login",
            json={"phone": "9999999999", "password": "secret123"},
        )
        assert old_login_response.status_code == 200
    finally:
        settings.app_env = original_app_env


def test_signup_creates_subscriber_account_and_hashes_password(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/auth/signup",
        json={
            "fullName": "Signup Subscriber",
            "phone": "7777777000",
            "email": "signup@example.com",
            "password": "signup-pass-123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "subscriber"
    assert body["owner_id"] is None
    assert body["subscriber_id"] is not None
    assert body["has_subscriber_profile"] is True
    assert body["user"]["roles"] == ["subscriber"]

    user = db_session.scalar(select(User).where(User.phone == "7777777000"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "7777777000"))
    assert user is not None
    assert subscriber is not None
    assert subscriber.owner_id is None
    assert subscriber.full_name == "Signup Subscriber"
    assert verify_password("signup-pass-123", user.password_hash)

    login_response = client.post(
        "/api/auth/login",
        json={"phone": "7777777000", "password": "signup-pass-123"},
    )
    assert login_response.status_code == 200


def test_login_resolves_roles_for_subscriber_only_and_owner_only_users(app, db_session):
    owner_only_user = User(
        email="owner-only@example.com",
        phone="7777777001",
        password_hash=hash_password("owner-only-pass"),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_only_user)
    db_session.flush()
    db_session.add(
        Owner(
            user_id=owner_only_user.id,
            display_name="Owner Only",
            business_name="Owner Only Chits",
            city="Chennai",
            state="Tamil Nadu",
            status="active",
        )
    )
    db_session.commit()

    client = TestClient(app)

    subscriber_response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert subscriber_response.status_code == 200
    assert subscriber_response.json()["user"] == {"id": 2, "roles": ["subscriber"]}

    owner_only_response = client.post(
        "/api/auth/login",
        json={"phone": "7777777001", "password": "owner-only-pass"},
    )
    assert owner_only_response.status_code == 200
    assert owner_only_response.json()["user"] == {"id": 3, "roles": ["owner"]}


def test_auth_me_returns_resolved_roles_for_current_user(app):
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "chit_owner"
    assert response.json()["roles"] == ["subscriber", "owner"]
    assert response.json()["owner_id"] == 1
    assert response.json()["subscriber_id"] == 1
    assert response.json()["user"] == {"id": 1, "roles": ["subscriber", "owner"]}


def test_auth_me_updates_roles_immediately_after_owner_profile_insert(app, db_session):
    subscriber_user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    assert subscriber_user is not None

    owner = Owner(
        user_id=subscriber_user.id,
        display_name="Subscriber Turned Owner",
        business_name="Subscriber Turned Owner Chits",
        city="Coimbatore",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.commit()

    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert login_response.status_code == 200

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "chit_owner"
    assert response.json()["roles"] == ["subscriber", "owner"]
    assert response.json()["user"] == {"id": subscriber_user.id, "roles": ["subscriber", "owner"]}


def test_signup_rejects_duplicate_phone(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/signup",
        json={
            "fullName": "Duplicate Phone",
            "phone": "9999999999",
            "email": "duplicate-phone@example.com",
            "password": "signup-pass-123",
        },
    )
    assert response.status_code == 409


def test_login_locks_phone_after_repeated_failures(app, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_max_attempts", 2, raising=False)
    monkeypatch.setattr(settings, "auth_login_attempt_window_seconds", 60, raising=False)
    monkeypatch.setattr(settings, "auth_login_cooldown_seconds", 120, raising=False)
    monkeypatch.setattr(auth_service, "_clock", lambda: 1_000_000, raising=False)

    client = TestClient(app)
    payload = {"phone": "9999999999", "password": "wrong-password"}

    first_response = client.post("/api/auth/login", json=payload)
    assert first_response.status_code == 401

    second_response = client.post("/api/auth/login", json=payload)
    assert second_response.status_code == 429
    assert second_response.headers["retry-after"] == "120"

    locked_response = client.post("/api/auth/login", json={"phone": "9999999999", "password": "secret123"})
    assert locked_response.status_code == 429
    assert locked_response.headers["retry-after"] == "120"


def test_successful_login_clears_previous_failures(app, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_max_attempts", 2, raising=False)
    monkeypatch.setattr(settings, "auth_login_attempt_window_seconds", 60, raising=False)
    monkeypatch.setattr(settings, "auth_login_cooldown_seconds", 120, raising=False)
    monkeypatch.setattr(auth_service, "_clock", lambda: 1_000_000, raising=False)

    client = TestClient(app)
    wrong_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "wrong-password"},
    )
    assert wrong_response.status_code == 401

    success_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert success_response.status_code == 200

    retry_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "wrong-password"},
    )
    assert retry_response.status_code == 401


def test_health_route_sets_local_dev_cors_headers(app):
    client = TestClient(app)
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_login_error_responses_keep_cors_headers(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "wrong-password"},
        headers={"Origin": "http://localhost:4173"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"


def test_owner_dashboard_preflight_allows_local_static_preview_origin(app):
    client = TestClient(app)
    response = client.options(
        "/api/reporting/owner/dashboard",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_owner_dashboard_preflight_allows_local_static_frontend_origin(app):
    client = TestClient(app)
    response = client.options(
        "/api/reporting/owner/dashboard",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
    assert response.headers["access-control-allow-credentials"] == "true"
