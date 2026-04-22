from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Owner, Subscriber, User


def _current_owner(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=None)


def _current_subscriber(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert subscriber is not None
    return CurrentUser(user=user, owner=None, subscriber=subscriber)


def _make_subscriber(db_session, *, phone: str, email: str, owner_id: int) -> Subscriber:
    user = User(
        email=email,
        phone=phone,
        password_hash="hash",
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


def _make_external_chit(db_session, *, subscriber_id: int, title: str = "Neighbourhood Chit") -> ExternalChit:
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


def _make_external_chit_entry(db_session, *, external_chit_id: int, entry_type: str = "paid") -> ExternalChitEntry:
    entry = ExternalChitEntry(
        external_chit_id=external_chit_id,
        entry_type=entry_type,
        entry_date=date(2026, 5, 10),
        amount=2500,
        description="Installment payment",
    )
    db_session.add(entry)
    db_session.flush()
    return entry


def test_validate_external_chit_create_payload_rejects_non_positive_amounts(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_create_payload

    payload = SimpleNamespace(
        subscriberId=2,
        title="Neighbourhood Chit",
        organizerName="Ravi",
        chitValue=0,
        installmentAmount=5000,
        cycleFrequency="monthly",
        startDate=date(2026, 5, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_create_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_create_payload_rejects_blank_required_fields(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_create_payload

    payload = SimpleNamespace(
        subscriberId=2,
        title="   ",
        organizerName="Ravi",
        chitValue=100000,
        installmentAmount=5000,
        cycleFrequency="monthly",
        startDate=date(2026, 5, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_create_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_create_payload_rejects_invalid_status(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_create_payload

    payload = SimpleNamespace(
        subscriberId=2,
        title="Neighbourhood Chit",
        organizerName="Ravi",
        chitValue=100000,
        installmentAmount=5000,
        cycleFrequency="monthly",
        startDate=date(2026, 5, 1),
        status="archived",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_create_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_create_payload_rejects_invalid_cycle_frequency(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_create_payload

    payload = SimpleNamespace(
        subscriberId=2,
        title="Neighbourhood Chit",
        organizerName="Ravi",
        chitValue=100000,
        installmentAmount=5000,
        cycleFrequency="daily",
        startDate=date(2026, 5, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_create_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_create_payload_accepts_valid_payload(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_create_payload

    payload = SimpleNamespace(
        subscriberId=2,
        title="Neighbourhood Chit",
        organizerName="Ravi",
        chitValue=100000,
        installmentAmount=5000,
        cycleFrequency="monthly",
        startDate=date(2026, 5, 1),
    )

    result = validate_external_chit_create_payload(payload)

    assert result["subscriberId"] == 2
    assert result["cycleFrequency"] == "monthly"
    assert result["chitValue"] == 100000.0


def test_validate_external_chit_access_allows_current_subscriber(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_access

    current_user = _current_subscriber(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id)
    db_session.commit()

    result = require_external_chit_access(db_session, current_user, chit.id)

    assert result.id == chit.id


def test_validate_external_chit_access_allows_owner_for_owned_subscriber_data(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_access

    current_user = _current_owner(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.owner_id == current_user.owner.id))
    assert subscriber is not None
    chit = _make_external_chit(db_session, subscriber_id=subscriber.id)
    db_session.commit()

    result = require_external_chit_access(db_session, current_user, chit.id)

    assert result.id == chit.id


def test_validate_external_chit_access_rejects_other_subscriber_update(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_access

    current_user = _current_subscriber(db_session)
    owner = db_session.scalar(select(Owner).where(Owner.id == current_user.subscriber.owner_id))
    assert owner is not None
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000201",
        email="foreign-subscriber@example.com",
        owner_id=owner.id,
    )
    chit = _make_external_chit(db_session, subscriber_id=foreign_subscriber.id)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_access(db_session, current_user, chit.id)

    assert exc_info.value.status_code == 403


def test_validate_external_chit_delete_rejects_other_subscriber_data(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_access

    current_user = _current_subscriber(db_session)
    owner = db_session.scalar(select(Owner).where(Owner.id == current_user.subscriber.owner_id))
    assert owner is not None
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000202",
        email="foreign-delete@example.com",
        owner_id=owner.id,
    )
    chit = _make_external_chit(db_session, subscriber_id=foreign_subscriber.id)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_access(db_session, current_user, chit.id)

    assert exc_info.value.status_code == 403


def test_validate_external_chit_entry_access_rejects_other_subscriber_delete(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_entry_access

    current_user = _current_subscriber(db_session)
    owner = db_session.scalar(select(Owner).where(Owner.id == current_user.subscriber.owner_id))
    assert owner is not None
    foreign_subscriber = _make_subscriber(
        db_session,
        phone="9000000203",
        email="foreign-entry@example.com",
        owner_id=owner.id,
    )
    chit = _make_external_chit(db_session, subscriber_id=foreign_subscriber.id)
    entry = _make_external_chit_entry(db_session, external_chit_id=chit.id)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_external_chit_entry_access(db_session, current_user, entry.id)

    assert exc_info.value.status_code == 403


def test_validate_external_chit_entry_payload_rejects_missing_amount_for_paid_entry(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_entry_payload

    payload = SimpleNamespace(
        entryType="paid",
        entryDate=date(2026, 5, 10),
        amount=None,
        description="Monthly payment",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_entry_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_entry_payload_accepts_note_without_amount(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_entry_payload

    payload = SimpleNamespace(
        entryType="note",
        entryDate=date(2026, 5, 10),
        amount=None,
        description="Reminder",
    )

    result = validate_external_chit_entry_payload(payload)

    assert result["entryType"] == "note"
    assert result["amount"] is None


def test_validate_external_chit_entry_access_allows_owner(app, db_session):
    from app.modules.external_chits.validation import require_external_chit_entry_access

    current_user = _current_owner(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.owner_id == current_user.owner.id))
    assert subscriber is not None
    chit = _make_external_chit(db_session, subscriber_id=subscriber.id)
    entry = _make_external_chit_entry(db_session, external_chit_id=chit.id)
    db_session.commit()

    result = require_external_chit_entry_access(db_session, current_user, entry.id)

    assert result.id == entry.id


def test_validate_external_chit_monthly_entry_payload_marks_manual_values_as_overrides(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_monthly_entry_payload

    payload = SimpleNamespace(
        monthNumber=2,
        bidAmount=20000,
        winnerType="other",
        sharePerSlot=2500,
        myPayable=15000,
    )

    result = validate_external_chit_monthly_entry_payload(payload)

    assert result["monthNumber"] == 2
    assert result["bidAmount"] == 20000
    assert result["winnerType"] == "OTHER"
    assert result["isBidOverridden"] is True
    assert result["isShareOverridden"] is True
    assert result["isPayableOverridden"] is True
    assert result["isPayoutOverridden"] is False


def test_validate_external_chit_monthly_entry_payload_rejects_negative_manual_values(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_monthly_entry_payload

    payload = SimpleNamespace(myPayout=-1)

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_monthly_entry_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_monthly_entry_payload_requires_value_when_override_flag_is_explicit(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_monthly_entry_payload

    payload = SimpleNamespace(isPayoutOverridden=True)

    with pytest.raises(HTTPException) as exc_info:
        validate_external_chit_monthly_entry_payload(payload)

    assert exc_info.value.status_code == 422


def test_validate_external_chit_entry_payload_allows_monthly_entries_without_amount_when_bid_is_missing(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_entry_payload

    payload = SimpleNamespace(
        entryType="paid",
        entryDate=date(2026, 5, 10),
        amount=None,
        description="Month saved without bid yet",
        monthNumber=2,
        bidAmount=None,
    )

    result = validate_external_chit_entry_payload(payload)

    assert result["entryType"] == "paid"
    assert result["amount"] is None


def test_validate_external_chit_entry_update_payload_ignores_omitted_monthly_fields(app, db_session):
    from app.modules.external_chits.validation import validate_external_chit_entry_update_payload

    payload = SimpleNamespace(description="Keep the rest unchanged")

    result = validate_external_chit_entry_update_payload(payload)

    assert result == {"description": "Keep the rest unchanged"}
