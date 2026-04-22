from datetime import date

from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership
from app.models.money import LedgerEntry, Payment
from app.modules.payments.ledger_service import create_payment_ledger_entry


def test_create_payment_ledger_entry_posts_group_scoped_row(app, db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="LEDGER-001",
        title="Ledger Group",
        chit_value=100000,
        installment_amount=5000,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=7,
        membership_status="active",
    )
    db_session.add(membership)
    db_session.flush()

    payment = Payment(
        owner_id=1,
        subscriber_id=2,
        membership_id=membership.id,
        installment_id=None,
        payment_type="installment",
        payment_method="upi",
        amount=25000,
        payment_date=date(2026, 5, 10),
        reference_no="UPI-LEDGER-001",
        recorded_by_user_id=1,
        status="recorded",
    )
    db_session.add(payment)
    db_session.flush()

    entry = create_payment_ledger_entry(db_session, payment)

    persisted = db_session.scalar(select(LedgerEntry).where(LedgerEntry.id == entry.id))
    assert persisted is not None
    assert persisted.owner_id == 1
    assert persisted.subscriber_id == 2
    assert persisted.group_id == group.id
    assert persisted.entry_date.isoformat() == "2026-05-10"
    assert persisted.entry_type == "payment"
    assert persisted.source_table == "payments"
    assert persisted.source_id == payment.id
    assert float(persisted.debit_amount) == 25000.0
    assert float(persisted.credit_amount) == 0.0
    assert "Ledger Group" in persisted.description
    assert "Subscriber" in persisted.description
    assert "UPI-LEDGER-001" in persisted.description
