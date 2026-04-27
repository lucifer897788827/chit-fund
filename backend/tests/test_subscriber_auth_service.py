from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import Owner, Subscriber, User
from app.modules.subscribers.auth_service import create_subscriber_user
from app.modules.subscribers.service import (
    create_subscriber,
    deactivate_admin_subscriber_profiles,
    ensure_subscriber_profile,
)


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


def test_ensure_subscriber_profile_rejects_admin_even_without_profile(app, db_session):
    admin = User(
        email="admin-profile@example.com",
        phone="9000000104",
        password_hash=create_subscriber_user.__globals__["hash_password"]("admin-pass"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    current_user = type("CurrentUserLike", (), {"user": admin, "owner": None, "subscriber": None})()

    with pytest.raises(HTTPException) as exc_info:
        ensure_subscriber_profile(db_session, current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin cannot have subscriber profile"


def test_ensure_subscriber_profile_rejects_admin_with_existing_profile(app, db_session):
    owner = db_session.scalar(select(Owner).order_by(Owner.id.asc()))
    assert owner is not None
    admin = User(
        email="admin-profile-2@example.com",
        phone="9000000105",
        password_hash=create_subscriber_user.__globals__["hash_password"]("admin-pass"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.flush()
    admin_subscriber = Subscriber(
        user_id=admin.id,
        owner_id=owner.id,
        full_name="Admin Profile",
        phone=admin.phone,
        email=admin.email,
        status="active",
    )
    db_session.add(admin_subscriber)
    db_session.commit()

    current_user = type("CurrentUserLike", (), {"user": admin, "owner": None, "subscriber": admin_subscriber})()

    with pytest.raises(HTTPException) as exc_info:
        ensure_subscriber_profile(db_session, current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin cannot have subscriber profile"


def test_deactivate_admin_subscriber_profiles_marks_admin_rows_inactive(app, db_session):
    owner = db_session.scalar(select(Owner).order_by(Owner.id.asc()))
    assert owner is not None
    admin = User(
        email="admin-cleanup@example.com",
        phone="9000000106",
        password_hash=create_subscriber_user.__globals__["hash_password"]("admin-pass"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.flush()
    admin_subscriber = Subscriber(
        user_id=admin.id,
        owner_id=owner.id,
        full_name="Admin Cleanup",
        phone=admin.phone,
        email=admin.email,
        status="active",
    )
    db_session.add(admin_subscriber)
    db_session.commit()

    updated_count = deactivate_admin_subscriber_profiles(db_session)

    db_session.refresh(admin_subscriber)

    assert updated_count == 1
    assert admin_subscriber.status == "inactive"
