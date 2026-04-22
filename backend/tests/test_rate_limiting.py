from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.rate_limiter import rate_limiter
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.user import Subscriber


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}
        self.deleted_keys: list[tuple[str, ...]] = []

    def incr(self, key: str) -> int:
        value = self.values.get(key, 0) + 1
        self.values[key] = value
        return value

    def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
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

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value, ex=None):
        self.values[key] = int(value) if value is not None else value
        if ex is not None:
            self.expirations[key] = ex
        return True


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    backend = FakeRedis()
    monkeypatch.setattr(rate_limiter, "_redis", backend, raising=False)
    rate_limiter.clear()
    yield backend
    rate_limiter.clear()


def _seed_payment_target(db_session):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="RL-001",
        title="Rate Limit Chit",
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


def test_login_rate_limit_uses_client_ip_bucket(app, monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60, raising=False)
    monkeypatch.setattr(settings, "rate_limit_requests", 1, raising=False)
    monkeypatch.setattr(rate_limiter, "_clock", lambda: 1_000_000, raising=False)

    client = TestClient(app)
    payload = {"phone": "9999999999", "password": "secret123"}

    first_response = client.post("/api/auth/login", json=payload)
    assert first_response.status_code == 200

    assert list(fake_redis.values) == ["rate_limit:ip:testclient:auth:login:16666"]
    assert fake_redis.values["rate_limit:ip:testclient:auth:login:16666"] == 1
    assert fake_redis.expirations["rate_limit:ip:testclient:auth:login:16666"] == 60

    second_response = client.post("/api/auth/login", json=payload)
    assert second_response.status_code == 429
    assert second_response.json()["detail"] == "Rate limit exceeded"


def test_authenticated_write_rate_limit_uses_user_bucket(app, db_session, monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60, raising=False)
    monkeypatch.setattr(settings, "rate_limit_requests", 1, raising=False)
    monkeypatch.setattr(rate_limiter, "_clock", lambda: 1_000_000, raising=False)

    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    _, group, membership, installment = _seed_payment_target(db_session)
    payload = {
        "ownerId": 1,
        "subscriberId": membership.subscriber_id,
        "membershipId": membership.id,
        "installmentId": installment.id,
        "paymentType": "installment",
        "paymentMethod": "cash",
        "amount": 1000,
        "paymentDate": "2026-05-11",
        "referenceNo": "RATE-LIMIT-001",
    }

    first_payment = client.post("/api/payments", headers=headers, json=payload)
    assert first_payment.status_code == 201
    assert first_payment.json()["groupId"] == group.id

    assert "rate_limit:user:1:payments:16666" in fake_redis.values
    assert fake_redis.values["rate_limit:user:1:payments:16666"] == 1

    second_payment = client.post("/api/payments", headers=headers, json=payload)
    assert second_payment.status_code == 429
    assert second_payment.json()["detail"] == "Rate limit exceeded"
