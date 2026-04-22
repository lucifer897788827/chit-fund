from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser, hash_password
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Owner, Subscriber, User


def _make_subscriber(
    db_session,
    *,
    phone: str,
    email: str,
    owner_id: int,
    password: str = "pass123",
) -> tuple[User, Subscriber]:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
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
    return user, subscriber


def _make_external_chit(db_session, *, subscriber_id: int, title: str) -> ExternalChit:
    chit = ExternalChit(
        subscriber_id=subscriber_id,
        title=title,
        organizer_name="Ravi",
        chit_value=100000,
        installment_amount=5000,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        status="active",
    )
    db_session.add(chit)
    db_session.flush()
    return chit


def _current_subscriber_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    owner = db_session.scalar(select(Owner).where(Owner.id == subscriber.owner_id)) if subscriber else None
    assert user is not None
    assert subscriber is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def test_require_external_chit_subscriber_returns_logged_in_subscriber(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_subscriber

    current_user = _current_subscriber_user(db_session)

    result = require_external_chit_subscriber(current_user)

    assert result is current_user.subscriber


def test_require_external_chit_subscriber_rejects_owner_without_subscriber_profile(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_subscriber

    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id)) if owner_user else None
    assert owner_user is not None
    assert owner is not None

    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=None)

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_subscriber(current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Subscriber profile required"


def test_require_external_chit_subscriber_access_allows_own_subscriber_id(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_subscriber_access

    current_user = _current_subscriber_user(db_session)

    result = require_external_chit_subscriber_access(current_user, current_user.subscriber.id)

    assert result == current_user.subscriber.id


def test_require_external_chit_subscriber_access_rejects_other_subscriber_id(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_subscriber_access

    current_user = _current_subscriber_user(db_session)
    other_owner = db_session.scalar(select(Owner).where(Owner.id == current_user.subscriber.owner_id))
    assert other_owner is not None
    _, other_subscriber = _make_subscriber(
        db_session,
        phone="9000000101",
        email="other-subscriber@example.com",
        owner_id=other_owner.id,
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_subscriber_access(current_user, other_subscriber.id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Cannot access another subscriber's external chit data"


def test_require_external_chit_access_allows_own_chit_row(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_access

    current_user = _current_subscriber_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="Own Chit")
    db_session.commit()

    result = require_external_chit_access(current_user, chit)

    assert result is chit


def test_require_external_chit_access_rejects_foreign_chit_row(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_access

    current_user = _current_subscriber_user(db_session)
    other_subscriber = db_session.scalar(
        select(Subscriber).where(Subscriber.id != current_user.subscriber.id)
    )
    assert other_subscriber is not None
    chit = _make_external_chit(db_session, subscriber_id=other_subscriber.id, title="Foreign Chit")
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_access(current_user, chit)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Cannot access another subscriber's external chit data"


def test_require_external_chit_entry_access_allows_entry_on_own_chit(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_entry_access

    current_user = _current_subscriber_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="Own Chit")
    entry = ExternalChitEntry(
        external_chit_id=chit.id,
        entry_type="paid",
        entry_date=date(2026, 5, 10),
        amount=2500,
        description="Installment payment",
    )
    db_session.add(entry)
    db_session.commit()

    result = require_external_chit_entry_access(current_user, entry, chit)

    assert result is entry


def test_require_external_chit_entry_access_rejects_entry_on_foreign_chit(app, db_session):
    from app.modules.external_chits.access_control import require_external_chit_entry_access

    current_user = _current_subscriber_user(db_session)
    other_subscriber = db_session.scalar(
        select(Subscriber).where(Subscriber.id != current_user.subscriber.id)
    )
    assert other_subscriber is not None
    foreign_chit = _make_external_chit(db_session, subscriber_id=other_subscriber.id, title="Foreign Chit")
    own_chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="Own Chit")
    entry = ExternalChitEntry(
        external_chit_id=foreign_chit.id,
        entry_type="note",
        entry_date=date(2026, 5, 10),
        amount=None,
        description="Foreign entry",
    )
    db_session.add_all([entry])
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_entry_access(current_user, entry, own_chit)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Cannot access another subscriber's external chit entry"
