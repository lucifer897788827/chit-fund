from datetime import datetime, timezone

from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership, Installment
from app.modules.payments.installment_service import build_membership_dues_snapshot_map, reconcile_installment_payment


def _seed_installment(db_session, *, paid_amount: float, balance_amount: float, status: str):
    group = ChitGroup(
        owner_id=1,
        group_code="REC-001",
        title="Reconciliation Group",
        chit_value=500000,
        installment_amount=25000,
        member_count=20,
        cycle_count=12,
        cycle_frequency="monthly",
        start_date=datetime(2026, 5, 1, tzinfo=timezone.utc).date(),
        first_auction_date=datetime(2026, 5, 10, tzinfo=timezone.utc).date(),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    installment = Installment(
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_date=datetime(2026, 5, 1, tzinfo=timezone.utc).date(),
        due_amount=25000,
        penalty_amount=0,
        paid_amount=paid_amount,
        balance_amount=balance_amount,
        status=status,
    )
    db_session.add(installment)
    db_session.commit()
    db_session.refresh(installment)
    return installment


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def test_reconcile_installment_payment_marks_partial_payment(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=0, balance_amount=25000, status="pending")
    group = db_session.get(ChitGroup, installment.group_id)
    assert group is not None
    paid_at = datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: paid_at)

    updated = reconcile_installment_payment(db_session, installment, group, amount=10000)

    assert updated.id == installment.id
    assert float(updated.paid_amount) == 10000.0
    assert float(updated.balance_amount) == 15000.0
    assert updated.status == "partial"
    assert _as_utc(updated.last_paid_at) == paid_at

    stored = db_session.scalar(select(Installment).where(Installment.id == installment.id))
    assert stored is not None
    assert float(stored.paid_amount) == 10000.0
    assert float(stored.balance_amount) == 15000.0
    assert stored.status == "partial"
    assert _as_utc(stored.last_paid_at) == paid_at


def test_reconcile_installment_payment_marks_full_payment(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=5000, balance_amount=20000, status="partial")
    group = db_session.get(ChitGroup, installment.group_id)
    assert group is not None
    paid_at = datetime(2026, 5, 12, 16, 45, tzinfo=timezone.utc)
    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: paid_at)

    updated = reconcile_installment_payment(db_session, installment, group, amount=20000)

    assert updated.id == installment.id
    assert float(updated.paid_amount) == 25000.0
    assert float(updated.balance_amount) == 0.0
    assert updated.status == "paid"
    assert _as_utc(updated.last_paid_at) == paid_at

    stored = db_session.scalar(select(Installment).where(Installment.id == installment.id))
    assert stored is not None
    assert float(stored.paid_amount) == 25000.0
    assert float(stored.balance_amount) == 0.0
    assert stored.status == "paid"
    assert _as_utc(stored.last_paid_at) == paid_at


def test_membership_dues_snapshot_applies_fixed_penalty_after_grace(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=0, balance_amount=25000, status="pending")
    group = db_session.get(ChitGroup, installment.group_id)
    assert group is not None
    group.penalty_enabled = True
    group.penalty_type = "FIXED"
    group.penalty_value = 500
    group.grace_period_days = 2
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc))
    snapshot = build_membership_dues_snapshot_map(db_session, [installment.membership_id])[installment.membership_id]

    assert float(snapshot.penalty_amount) == 500.0
    assert float(snapshot.total_due) == 25500.0
    assert float(snapshot.outstanding_amount) == 25500.0
    assert float(snapshot.arrears_amount) == 25500.0


def test_reconcile_installment_payment_uses_penalized_balance(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=0, balance_amount=25000, status="pending")
    group = db_session.get(ChitGroup, installment.group_id)
    assert group is not None
    group.penalty_enabled = True
    group.penalty_type = "PERCENTAGE"
    group.penalty_value = 10
    group.grace_period_days = 0
    db_session.commit()

    paid_at = datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: paid_at)

    updated = reconcile_installment_payment(db_session, installment, group, amount=26000)

    assert float(updated.penalty_amount) == 2500.0
    assert float(updated.paid_amount) == 26000.0
    assert float(updated.balance_amount) == 1500.0
    assert updated.status == "partial"


def test_membership_dues_snapshot_applies_decimal_percentage_penalty(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=0, balance_amount=25000, status="pending")
    group = db_session.get(ChitGroup, installment.group_id)
    assert group is not None
    group.penalty_enabled = True
    group.penalty_type = "PERCENTAGE"
    group.penalty_value = 7.5
    group.grace_period_days = 0
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc))
    snapshot = build_membership_dues_snapshot_map(db_session, [installment.membership_id])[installment.membership_id]

    assert float(snapshot.penalty_amount) == 1875.0
    assert float(snapshot.total_due) == 26875.0
    assert float(snapshot.outstanding_amount) == 26875.0


def test_membership_dues_snapshot_rolls_arrears_into_next_due_amount(app, db_session, monkeypatch):
    installment = _seed_installment(db_session, paid_amount=0, balance_amount=1000, status="pending")
    group = db_session.get(ChitGroup, installment.group_id)
    membership = db_session.get(GroupMembership, installment.membership_id)
    assert group is not None
    assert membership is not None

    installment.due_amount = 1000
    installment.balance_amount = 400
    installment.paid_amount = 600
    installment.status = "partial"
    db_session.add(
        Installment(
            group_id=group.id,
            membership_id=membership.id,
            cycle_no=2,
            due_date=datetime(2026, 6, 1, tzinfo=timezone.utc).date(),
            due_amount=1000,
            penalty_amount=0,
            paid_amount=0,
            balance_amount=1000,
            status="pending",
        )
    )
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc))
    snapshot = build_membership_dues_snapshot_map(db_session, [membership.id])[membership.id]

    assert float(snapshot.arrears_amount) == 400.0
    assert float(snapshot.next_due_amount) == 1400.0
    assert float(snapshot.outstanding_amount) == 1400.0
    assert snapshot.next_due_date == datetime(2026, 6, 1, tzinfo=timezone.utc).date()
