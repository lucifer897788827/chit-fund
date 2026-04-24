from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import LedgerEntry, Payment
from app.models.user import Subscriber


def _build_payment_description(db: Session, payment: Payment) -> str:
    subscriber = db.get(Subscriber, payment.subscriber_id)
    membership = db.get(GroupMembership, payment.membership_id) if payment.membership_id else None
    group = db.get(ChitGroup, membership.group_id) if membership else None

    parts: list[str] = [f"{payment.payment_type.replace('_', ' ').title()} payment"]
    if subscriber is not None:
        parts.append(f"for {subscriber.full_name}")
    if group is not None:
        parts.append(f"in {group.title}")
    if payment.reference_no:
        parts.append(f"(ref {payment.reference_no})")

    return " ".join(parts)[:255]


def create_payment_ledger_entry(db: Session, payment: Payment) -> LedgerEntry:
    return ensure_payment_ledger_entry(db, payment)


def ensure_payment_ledger_entry(db: Session, payment: Payment) -> LedgerEntry:
    db.flush()
    existing_entry = db.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payments",
            LedgerEntry.source_id == payment.id,
        )
    )
    if existing_entry is not None:
        return existing_entry

    membership = db.get(GroupMembership, payment.membership_id) if payment.membership_id else None
    installment = db.get(Installment, payment.installment_id) if payment.installment_id else None
    entry = LedgerEntry(
        owner_id=payment.owner_id,
        entry_date=payment.payment_date,
        entry_type="payment",
        source_table="payments",
        source_id=payment.id,
        subscriber_id=payment.subscriber_id,
        group_id=membership.group_id if membership else installment.group_id if installment else None,
        debit_amount=payment.amount,
        credit_amount=0,
        description=_build_payment_description(db, payment),
    )
    try:
        with db.begin_nested():
            db.add(entry)
            db.flush()
    except IntegrityError:
        existing_entry = db.scalar(
            select(LedgerEntry).where(
                LedgerEntry.source_table == "payments",
                LedgerEntry.source_id == payment.id,
            )
        )
        if existing_entry is not None:
            return existing_entry
        raise
    return entry
