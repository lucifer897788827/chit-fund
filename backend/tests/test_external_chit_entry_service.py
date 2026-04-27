from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser, hash_password
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Subscriber, User, Owner


def _subscriber_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    owner = db_session.scalar(select(Owner).where(Owner.id == subscriber.owner_id)) if subscriber else None
    assert user is not None
    assert subscriber is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    assert user is not None
    assert subscriber is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _make_external_chit(db_session, *, subscriber_id: int, title: str) -> ExternalChit:
    chit = ExternalChit(
        subscriber_id=subscriber_id,
        title=title,
        organizer_name="Ravi",
        chit_value=100000,
        installment_amount=5000,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=None,
        status="active",
        notes=None,
    )
    db_session.add(chit)
    db_session.flush()
    return chit


def test_create_external_chit_entry_persists_and_returns_clean_response(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=2500,
        description="Monthly payment",
    )

    result = create_external_chit_entry(db_session, payload, current_user)

    assert result["id"] > 0
    assert result["externalChitId"] == chit.id
    assert result["entryType"] == "paid"
    assert result["entryDate"] == date(2026, 4, 10)
    assert result["amount"] == 2500.0
    assert result["description"] == "Monthly payment"
    assert result["monthNumber"] is None
    assert result["bidAmount"] is None
    assert result["winnerType"] is None
    assert result["winnerName"] is None
    assert result["sharePerSlot"] is None
    assert result["myShare"] is None
    assert result["myPayable"] is None
    assert result["myPayout"] is None
    assert result["isBidOverridden"] is False
    assert result["isShareOverridden"] is False
    assert result["isPayableOverridden"] is False
    assert result["isPayoutOverridden"] is False
    assert result["createdAt"] is not None
    persisted = db_session.scalar(select(ExternalChitEntry).where(ExternalChitEntry.id == result["id"]))
    assert persisted is not None
    assert persisted.external_chit_id == chit.id
    assert persisted.entry_type == "paid"


def test_list_external_chit_entries_returns_chronological_history(app, db_session):
    from app.modules.external_chits.entry_service import list_external_chit_entries

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.add_all(
        [
            ExternalChitEntry(
                external_chit_id=chit.id,
                entry_type="note",
                entry_date=date(2026, 4, 12),
                amount=None,
                description="Later note",
            ),
            ExternalChitEntry(
                external_chit_id=chit.id,
                entry_type="due",
                entry_date=date(2026, 4, 10),
                amount=5000,
                description="Installment due",
            ),
        ]
    )
    db_session.commit()

    result = list_external_chit_entries(db_session, chit.id, current_user)

    assert [row["entryDate"] for row in result] == [date(2026, 4, 10), date(2026, 4, 12)]
    assert result[0]["entryType"] == "due"
    assert result[1]["entryType"] == "note"


def test_create_external_chit_entry_rejects_chit_not_owned_by_current_subscriber(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    other_subscriber = db_session.scalar(
        select(Subscriber).where(Subscriber.id != current_user.subscriber.id)
    )
    assert other_subscriber is not None
    foreign_chit = _make_external_chit(db_session, subscriber_id=other_subscriber.id, title="Foreign Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=foreign_chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=2500,
        description="Unauthorized payment",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 403


def test_create_external_chit_entry_allows_owner_participant(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _owner_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="Owner Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=2500,
        description="Owner payment",
    )

    result = create_external_chit_entry(db_session, payload, current_user)

    assert result["externalChitId"] == chit.id
    assert result["description"] == "Owner payment"


def test_create_external_chit_entry_rejects_admin_even_with_subscriber_profile(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id)) if owner_user else None
    assert owner is not None
    admin_user = User(
        email="entry-admin@example.com",
        phone="9000000188",
        password_hash=hash_password("adminpass"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.flush()
    admin_subscriber = Subscriber(
        user_id=admin_user.id,
        owner_id=owner.id,
        full_name="Entry Admin",
        phone=admin_user.phone,
        email=admin_user.email,
        status="active",
    )
    db_session.add(admin_subscriber)
    db_session.flush()
    chit = _make_external_chit(db_session, subscriber_id=admin_subscriber.id, title="Admin Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=2500,
        description="Admin payment",
    )

    current_user = CurrentUser(user=admin_user, owner=None, subscriber=admin_subscriber)

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Subscriber profile required"


def test_owner_without_subscriber_profile_auto_creates_before_entry_access(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id)) if owner_user else None
    owner_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id)) if owner_user else None
    assert owner_user is not None
    assert owner is not None
    assert owner_subscriber is not None

    chit = _make_external_chit(db_session, subscriber_id=owner_subscriber.id, title="Legacy Owner Chit")
    db_session.delete(owner_subscriber)
    db_session.commit()

    recreated_subscriber = Subscriber(
        user_id=owner_user.id,
        owner_id=owner.id,
        full_name="Owner One",
        phone=owner_user.phone,
        email=owner_user.email,
        status="active",
        auto_created=True,
    )
    db_session.add(recreated_subscriber)
    db_session.commit()
    db_session.refresh(recreated_subscriber)
    chit.subscriber_id = recreated_subscriber.id
    db_session.add(chit)
    db_session.commit()

    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=None)
    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=2500,
        description="Auto-created owner payment",
    )

    result = create_external_chit_entry(db_session, payload, current_user)

    assert result["externalChitId"] == chit.id
    refreshed_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id))
    assert refreshed_subscriber is not None
    assert refreshed_subscriber.auto_created is True


def test_create_external_chit_entry_rejects_invalid_entry_type(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="refund",
        entryDate=date(2026, 4, 10),
        amount=1000,
        description="Invalid type",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422


def test_create_external_chit_entry_rejects_future_entry_date(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="due",
        entryDate=date(2026, 6, 1),
        amount=1000,
        description="Future date",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422


def test_create_external_chit_entry_rejects_missing_amount_for_paid_entry(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=None,
        description="No amount",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422


def test_create_external_chit_entry_rejects_blank_description(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="note",
        entryDate=date(2026, 4, 10),
        amount=None,
        description="   ",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422


def test_create_external_chit_entry_persists_monthly_override_fields_without_changing_response_shape(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    chit.monthly_installment = 10000
    chit.total_members = 10
    chit.user_slots = 2
    chit.first_month_organizer = False
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="won",
        entryDate=date(2026, 4, 10),
        amount=20000,
        description="Month result",
        monthNumber=2,
        bidAmount=20000,
        winnerType="SELF",
        sharePerSlot=2500,
        myShare=5000,
        myPayable=15000,
        myPayout=63000,
    )

    result = create_external_chit_entry(db_session, payload, current_user)

    assert result["id"] > 0
    assert result["externalChitId"] == chit.id
    assert result["entryType"] == "won"
    assert result["entryDate"] == date(2026, 4, 10)
    assert result["amount"] == 20000.0
    assert result["description"] == "Month result"
    assert result["monthNumber"] == 2
    assert result["bidAmount"] == 20000
    assert result["winnerType"] == "SELF"
    assert result["winnerName"] is None
    assert result["sharePerSlot"] == 2500
    assert result["myShare"] == 5000
    assert result["myPayable"] == 15000
    assert result["myPayout"] == 63000
    assert result["isBidOverridden"] is True
    assert result["isShareOverridden"] is True
    assert result["isPayableOverridden"] is True
    assert result["isPayoutOverridden"] is True
    assert result["createdAt"] is not None
    persisted = db_session.scalar(select(ExternalChitEntry).where(ExternalChitEntry.id == result["id"]))
    assert persisted is not None
    assert persisted.month_number == 2
    assert persisted.bid_amount == 20000
    assert persisted.winner_type == "SELF"
    assert persisted.winner_name is None
    assert persisted.share_per_slot == 2500
    assert persisted.my_share == 5000
    assert persisted.my_payable == 15000
    assert persisted.my_payout == 63000
    assert persisted.is_bid_overridden is True
    assert persisted.is_share_overridden is True
    assert persisted.is_payable_overridden is True
    assert persisted.is_payout_overridden is True


def test_create_external_chit_entry_allows_monthly_entry_without_bid_and_uses_safe_zero_defaults(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    chit.monthly_installment = 10000
    chit.total_members = 10
    chit.total_months = 20
    chit.user_slots = 2
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=None,
        description="Month saved before bid",
        monthNumber=2,
        bidAmount=None,
        winnerType="OTHER",
    )

    result = create_external_chit_entry(db_session, payload, current_user)

    assert result["amount"] is None
    assert result["monthNumber"] == 2
    assert result["bidAmount"] is None
    assert result["sharePerSlot"] == 0
    assert result["myShare"] == 0
    assert result["myPayable"] == 0
    assert result["myPayout"] == 0


def test_create_external_chit_entry_rejects_duplicate_month_number(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    chit.monthly_installment = 10000
    chit.total_members = 10
    chit.total_months = 20
    chit.user_slots = 2
    db_session.add(
        ExternalChitEntry(
            external_chit_id=chit.id,
            entry_type="paid",
            entry_date=date(2026, 4, 10),
            amount=20000,
            description="Month one",
            month_number=2,
        )
    )
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 11),
        amount=18000,
        description="Duplicate month",
        monthNumber=2,
        bidAmount=18000,
        winnerType="OTHER",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Month number already exists for this chit"


def test_create_external_chit_entry_rejects_out_of_order_month_number(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    chit.monthly_installment = 10000
    chit.total_members = 10
    chit.total_months = 20
    chit.user_slots = 2
    db_session.add(
        ExternalChitEntry(
            external_chit_id=chit.id,
            entry_type="paid",
            entry_date=date(2026, 4, 12),
            amount=20000,
            description="Later month",
            month_number=3,
        )
    )
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 11),
        amount=18000,
        description="Earlier month added later",
        monthNumber=2,
        bidAmount=18000,
        winnerType="OTHER",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Month entries must be added in ascending order"


def test_create_external_chit_entry_rejects_month_number_beyond_total_months(app, db_session):
    from app.modules.external_chits.entry_service import create_external_chit_entry

    current_user = _subscriber_current_user(db_session)
    chit = _make_external_chit(db_session, subscriber_id=current_user.subscriber.id, title="My Chit")
    chit.monthly_installment = 10000
    chit.total_members = 10
    chit.total_months = 3
    chit.user_slots = 2
    db_session.commit()

    payload = SimpleNamespace(
        externalChitId=chit.id,
        entryType="paid",
        entryDate=date(2026, 4, 10),
        amount=18000,
        description="Too late month",
        monthNumber=4,
        bidAmount=18000,
        winnerType="OTHER",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_external_chit_entry(db_session, payload, current_user)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Month number cannot exceed total months"
