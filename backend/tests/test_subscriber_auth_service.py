from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import Subscriber, User
from app.modules.subscribers.auth_service import create_subscriber_user
from app.modules.subscribers.service import create_subscriber


def test_create_subscriber_user_requires_password():
    payload = SimpleNamespace(
        fullName="Subscriber Three",
        phone="7777777777",
        email="subscriber3@example.com",
        password="",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_subscriber_user(payload)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Subscriber password is required"


def test_create_subscriber_hashes_password_and_supports_login(app, db_session):
    payload = SimpleNamespace(
        ownerId=1,
        fullName="Subscriber Three",
        phone="7777777777",
        email="subscriber3@example.com",
        password="fresh-pass-123",
    )

    result = create_subscriber(db_session, payload)

    assert result["phone"] == "7777777777"

    user = db_session.scalar(select(User).where(User.phone == "7777777777"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "7777777777"))
    assert user is not None
    assert subscriber is not None
    assert user.password_hash
    assert user.password_hash != "fresh-pass-123"
    assert verify_password("fresh-pass-123", user.password_hash)

    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "7777777777", "password": "fresh-pass-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "subscriber"
    assert body["subscriber_id"] == subscriber.id
    assert body["has_subscriber_profile"] is True
