from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.user import Owner, Subscriber, User
from app.modules.subscribers.crud_service import (
    list_subscribers,
    soft_delete_subscriber,
    update_subscriber,
)


def _owner_current_user(db_session, phone: str = "9999999999") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def test_list_subscribers_returns_only_current_owners_subscribers(app, db_session):
    owner_user = User(
        email="owner-two@example.com",
        phone="9999999998",
        password_hash="x",
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_user)
    db_session.flush()
    other_owner = Owner(
        user_id=owner_user.id,
        display_name="Owner Two",
        business_name="Owner Two Chits",
        city="Salem",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(other_owner)
    db_session.flush()

    db_session.add(
        Subscriber(
            user_id=owner_user.id,
            owner_id=other_owner.id,
            full_name="Other Owner Subscriber",
            phone="9999999000",
            email="other@example.com",
            status="active",
        )
    )
    db_session.commit()

    current_user = _owner_current_user(db_session)

    result = list_subscribers(db_session, current_user)

    assert {row["phone"] for row in result} == {"9999999999", "8888888888"}
    assert all(row["ownerId"] == current_user.owner.id for row in result)
    assert result[0]["ownerId"] == current_user.owner.id


def test_update_subscriber_rejects_cross_owner_access(app, db_session):
    owner_user = User(
        email="owner-two@example.com",
        phone="9999999988",
        password_hash="x",
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_user)
    db_session.flush()
    other_owner = Owner(
        user_id=owner_user.id,
        display_name="Owner Two",
        business_name="Owner Two Chits",
        city="Salem",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(other_owner)
    db_session.flush()

    foreign_subscriber_user = User(
        email="foreign@example.com",
        phone="9999999977",
        password_hash="x",
        role="subscriber",
        is_active=True,
    )
    db_session.add(foreign_subscriber_user)
    db_session.flush()
    foreign_subscriber = Subscriber(
        user_id=foreign_subscriber_user.id,
        owner_id=other_owner.id,
        full_name="Foreign Subscriber",
        phone=foreign_subscriber_user.phone,
        email=foreign_subscriber_user.email,
        status="active",
    )
    db_session.add(foreign_subscriber)
    db_session.commit()

    current_user = _owner_current_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        update_subscriber(
            db_session,
            foreign_subscriber.id,
            SimpleNamespace(fullName="Renamed Subscriber", phone="7777000001", email=None),
            current_user,
        )

    assert exc_info.value.status_code == 403


def test_soft_delete_subscriber_marks_record_deleted_and_keeps_it_in_owner_list(app, db_session):
    current_user = _owner_current_user(db_session)
    target = db_session.scalar(
        select(Subscriber).where(
            Subscriber.owner_id == current_user.owner.id,
            Subscriber.phone == "8888888888",
        )
    )
    assert target is not None

    deleted = soft_delete_subscriber(db_session, target.id, current_user)

    assert deleted["status"] == "deleted"
    refreshed = db_session.scalar(select(Subscriber).where(Subscriber.id == target.id))
    assert refreshed is not None
    assert refreshed.status == "deleted"

    result = list_subscribers(db_session, current_user)
    deleted_row = next(row for row in result if row["id"] == target.id)
    assert deleted_row["status"] == "deleted"
