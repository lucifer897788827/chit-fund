from datetime import date

from sqlalchemy import inspect

from app.core import database
from app.models.external import ExternalChit, ExternalChitEntry


def test_external_chit_schema_supports_monthly_ledger_fields(app, db_session):
    chit = ExternalChit(
        subscriber_id=1,
        user_id=1,
        title="Legacy compatible chit",
        name="Monthly ledger chit",
        organizer_name="Outside Organizer",
        chit_value=100000,
        installment_amount=10000,
        monthly_installment=10000,
        total_members=10,
        total_months=20,
        user_slots=2,
        first_month_organizer=False,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        status="active",
    )
    db_session.add(chit)
    db_session.commit()

    entry = ExternalChitEntry(
        external_chit_id=chit.id,
        month_number=1,
        bid_amount=20000,
        winner_type="OTHER",
        winner_name="Ravi",
        share_per_slot=2000,
        my_share=4000,
        my_payable=16000,
        my_payout=0,
        is_bid_overridden=False,
        is_share_overridden=False,
        is_payable_overridden=False,
        is_payout_overridden=False,
        entry_type="monthly_ledger",
        entry_date=date(2026, 5, 1),
        amount=20000,
        description="Month 1",
    )
    db_session.add(entry)
    db_session.commit()

    db_session.refresh(chit)
    db_session.refresh(entry)

    assert chit.user_id == 1
    assert chit.name == "Monthly ledger chit"
    assert chit.monthly_installment == 10000
    assert chit.total_members == 10
    assert chit.total_months == 20
    assert chit.user_slots == 2
    assert chit.first_month_organizer is False
    assert entry.month_number == 1
    assert entry.bid_amount == 20000
    assert entry.winner_type == "OTHER"
    assert entry.share_per_slot == 2000
    assert entry.my_share == 4000
    assert entry.my_payable == 16000
    assert entry.my_payout == 0


def test_external_chit_tables_expose_monthly_ledger_columns(app):
    inspector = inspect(database.engine)
    chit_columns = {column["name"] for column in inspector.get_columns("external_chits")}
    entry_columns = {column["name"] for column in inspector.get_columns("external_chit_entries")}

    assert {"user_id", "name", "monthly_installment", "total_members", "total_months", "user_slots", "first_month_organizer"} <= chit_columns
    assert {
        "month_number",
        "bid_amount",
        "winner_type",
        "winner_name",
        "share_per_slot",
        "my_share",
        "my_payable",
        "my_payout",
        "is_bid_overridden",
        "is_share_overridden",
        "is_payable_overridden",
        "is_payout_overridden",
        "updated_at",
    } <= entry_columns
