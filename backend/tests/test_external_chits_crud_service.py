from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.security import CurrentUser, hash_password
from app.models.external import ExternalChit
from app.models.user import Owner, Subscriber, User
from app.modules.external_chits.crud_service import (
    create_external_chit as create_external_chit_record,
    delete_external_chit,
    list_external_chits,
    update_external_chit,
)
from app.modules.external_chits.service import create_external_chit as create_external_chit_service


def _owner_current_user(db_session, phone: str = "9999999999") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _subscriber_current_user(db_session, phone: str = "8888888888") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return CurrentUser(user=user, owner=None, subscriber=subscriber)


def _make_owner(db_session, *, phone: str, email: str) -> Owner:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password("ownerpass"),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    owner = Owner(
        user_id=user.id,
        display_name="Owner",
        business_name="Owner Chits",
        city="Chennai",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.flush()
    return owner


def _make_subscriber(db_session, *, phone: str, email: str, owner_id: int) -> Subscriber:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password("pass123"),
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner_id,
        full_name="Subscriber",
        phone=phone,
        email=email,
        status="active",
    )
    db_session.add(subscriber)
    db_session.flush()
    return subscriber


def test_create_external_chit_rejects_foreign_subscriber_for_owner(app, db_session):
    current_user = _owner_current_user(db_session)
    other_owner = _make_owner(db_session, phone="9999999988", email="other-owner@example.com")
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000001",
        email="foreign-subscriber@example.com",
        owner_id=other_owner.id,
    )
    db_session.commit()

    payload = SimpleNamespace(
        subscriberId=foreign_subscriber.id,
        title="Foreign Chit",
        organizerName="Outside Organizer",
        chitValue=100000,
        installmentAmount=5000,
        cycleFrequency="monthly",
        startDate=date(2026, 5, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_record(db_session, payload, current_user)

    assert exc_info.value.status_code == 403


def test_create_and_list_external_chits_are_scoped_to_current_subscriber(app, db_session):
    current_user = _subscriber_current_user(db_session)

    created = create_external_chit_service(
        db_session,
        SimpleNamespace(
            subscriberId=current_user.subscriber.id,
            title="Subscriber Chit",
            organizerName="Ravi",
            chitValue=100000,
            installmentAmount=5000,
            cycleFrequency="monthly",
            startDate=date(2026, 5, 1),
        ),
        current_user,
    )
    assert created["subscriberId"] == current_user.subscriber.id
    assert created["status"] == "active"

    other_owner = _make_owner(db_session, phone="9999999988", email="other-owner@example.com")
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000002",
        email="foreign-subscriber@example.com",
        owner_id=other_owner.id,
    )
    db_session.add(
        ExternalChit(
            subscriber_id=foreign_subscriber.id,
            title="Foreign Chit",
            organizer_name="Other Organizer",
            chit_value=100000,
            installment_amount=5000,
            cycle_frequency="monthly",
            start_date=date(2026, 5, 1),
            status="active",
        )
    )
    db_session.commit()

    result = list_external_chits(db_session, current_user, current_user.subscriber.id)

    assert [row["title"] for row in result] == ["Subscriber Chit"]
    assert all(row["subscriberId"] == current_user.subscriber.id for row in result)


def test_update_external_chit_rejects_cross_subscriber_access(app, db_session):
    current_user = _subscriber_current_user(db_session)
    other_owner = _make_owner(db_session, phone="9999999988", email="other-owner@example.com")
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000003",
        email="foreign-subscriber@example.com",
        owner_id=other_owner.id,
    )
    chit = ExternalChit(
        subscriber_id=foreign_subscriber.id,
        title="Foreign Chit",
        organizer_name="Other Organizer",
        chit_value=100000,
        installment_amount=5000,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        status="active",
    )
    db_session.add(chit)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        update_external_chit(
            db_session,
            chit.id,
            SimpleNamespace(title="Renamed Chit"),
            current_user,
        )

    assert exc_info.value.status_code == 403


def test_delete_external_chit_marks_deleted_and_keeps_record_visible_to_owner(app, db_session):
    current_user = _owner_current_user(db_session)
    target = db_session.scalar(
        select(ExternalChit).where(
            ExternalChit.subscriber_id == current_user.subscriber.id,
            ExternalChit.title == "Owner One External Chit",
        )
    )
    if target is None:
        target = ExternalChit(
            subscriber_id=current_user.subscriber.id,
            title="Owner One External Chit",
            organizer_name="Ravi",
            chit_value=100000,
            installment_amount=5000,
            cycle_frequency="monthly",
            start_date=date(2026, 5, 1),
            status="active",
        )
        db_session.add(target)
        db_session.commit()
        db_session.refresh(target)

    deleted = delete_external_chit(db_session, target.id, current_user)

    assert deleted["status"] == "deleted"
    refreshed = db_session.scalar(select(ExternalChit).where(ExternalChit.id == target.id))
    assert refreshed is not None
    assert refreshed.status == "deleted"

    listed = list_external_chits(db_session, current_user, current_user.subscriber.id)
    assert any(row["id"] == target.id and row["status"] == "deleted" for row in listed)


def test_update_external_chit_can_mark_inactive(app, db_session):
    current_user = _owner_current_user(db_session)
    target = db_session.scalar(
        select(ExternalChit).where(
            ExternalChit.subscriber_id == current_user.subscriber.id,
            ExternalChit.title == "Inactive Candidate",
        )
    )
    if target is None:
        target = ExternalChit(
            subscriber_id=current_user.subscriber.id,
            title="Inactive Candidate",
            organizer_name="Ravi",
            chit_value=100000,
            installment_amount=5000,
            cycle_frequency="monthly",
            start_date=date(2026, 5, 1),
            status="active",
        )
        db_session.add(target)
        db_session.commit()
        db_session.refresh(target)

    updated = update_external_chit(
        db_session,
        target.id,
        SimpleNamespace(status="inactive"),
        current_user,
    )

    assert updated["status"] == "inactive"
    refreshed = db_session.scalar(select(ExternalChit).where(ExternalChit.id == target.id))
    assert refreshed is not None
    assert refreshed.status == "inactive"


def test_owner_without_subscriber_profile_auto_creates_profile_for_external_chits(app, db_session):
    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id)) if owner_user else None
    owner_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id)) if owner_user else None
    assert owner_user is not None
    assert owner is not None
    assert owner_subscriber is not None

    db_session.execute(delete(Subscriber).where(Subscriber.id == owner_subscriber.id))
    db_session.commit()

    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=None)

    created = create_external_chit_service(
        db_session,
        SimpleNamespace(
            title="Auto Created Owner Chit",
            organizerName="Ravi",
            chitValue=100000,
            installmentAmount=5000,
            cycleFrequency="monthly",
            startDate=date(2026, 5, 1),
        ),
        current_user,
    )

    created_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id))
    assert created_subscriber is not None
    assert created_subscriber.auto_created is True
    assert created_subscriber.owner_id == owner.id
    assert current_user.subscriber is not None
    assert current_user.subscriber.id == created_subscriber.id
    assert created["subscriberId"] == created_subscriber.id
