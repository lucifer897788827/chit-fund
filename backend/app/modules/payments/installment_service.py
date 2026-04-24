from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from datetime import date
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.time import utcnow
from app.models.chit import ChitGroup, Installment
from app.models.money import Payment
from app.modules.payments.auction_payout_engine import MembershipPayableBreakdown


def _add_months(base_date: date, month_offset: int) -> date:
    month_index = base_date.month - 1 + month_offset
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = (
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    )
    day = min(base_date.day, month_lengths[month - 1])
    return date(year, month, day)


def _calculate_due_date(start_date: date, cycle_frequency: str, cycle_no: int) -> date:
    if cycle_frequency == "weekly":
        return start_date + timedelta(days=(cycle_no - 1) * 7)
    return _add_months(start_date, cycle_no - 1)


def _normalize_penalty_type(value: str | None) -> str | None:
    normalized_value = (value or "").strip().upper()
    if normalized_value in {"FIXED", "PERCENTAGE"}:
        return normalized_value
    return None


@dataclass(frozen=True, slots=True)
class InstallmentFinancialSnapshot:
    installment_id: int
    membership_id: int
    group_id: int
    cycle_no: int
    due_date: date
    due_amount: int
    penalty_amount: int
    total_due_amount: int
    paid_amount: int
    balance_amount: int
    status: str


@dataclass(frozen=True, slots=True)
class MembershipDuesSnapshot:
    membership_id: int
    penalty_amount: int
    payment_status: str
    arrears_amount: int
    next_due_amount: int
    next_due_date: date | None
    total_due: int
    total_paid: int
    outstanding_amount: int

    def as_dict(self) -> dict:
        payload = {
            "paymentStatus": self.payment_status,
            "arrearsAmount": self.arrears_amount,
            "nextDueAmount": self.next_due_amount,
            "nextDueDate": self.next_due_date,
            "totalDue": self.total_due,
            "totalPaid": self.total_paid,
            "outstandingAmount": self.outstanding_amount,
        }
        if self.penalty_amount > 0:
            payload["penaltyAmount"] = self.penalty_amount
        return payload


def build_installment_financial_snapshot(
    installment: Installment,
    group: ChitGroup | None,
    *,
    as_of_date: date,
) -> InstallmentFinancialSnapshot:
    due_amount = money_int(installment.due_amount)
    paid_amount = money_int(installment.paid_amount)
    penalty_amount = 0

    if group is not None and bool(getattr(group, "penalty_enabled", False)):
        normalized_penalty_type = _normalize_penalty_type(getattr(group, "penalty_type", None))
        raw_penalty_value = getattr(group, "penalty_value", None)
        grace_period_days = max(int(getattr(group, "grace_period_days", 0) or 0), 0)
        penalty_cutoff_date = installment.due_date + timedelta(days=grace_period_days)

        if normalized_penalty_type is not None and raw_penalty_value is not None and as_of_date > penalty_cutoff_date:
            if normalized_penalty_type == "FIXED":
                penalty_value = money_int(raw_penalty_value)
                if penalty_value > 0:
                    penalty_amount = penalty_value
            else:
                try:
                    penalty_percentage = Decimal(str(raw_penalty_value))
                except (InvalidOperation, ValueError):
                    penalty_percentage = Decimal("0")
                if penalty_percentage > 0:
                    penalty_amount = int((Decimal(due_amount) * penalty_percentage) / Decimal("100"))

    total_due_amount = due_amount + penalty_amount
    balance_amount = max(total_due_amount - paid_amount, 0)

    if balance_amount <= 0:
        status = "paid"
    elif paid_amount > 0:
        status = "partial"
    else:
        status = "pending"

    return InstallmentFinancialSnapshot(
        installment_id=installment.id,
        membership_id=installment.membership_id,
        group_id=installment.group_id,
        cycle_no=installment.cycle_no,
        due_date=installment.due_date,
        due_amount=due_amount,
        penalty_amount=penalty_amount,
        total_due_amount=total_due_amount,
        paid_amount=paid_amount,
        balance_amount=balance_amount,
        status=status,
    )


def _build_membership_dues_snapshot(
    membership_id: int,
    installments: list[InstallmentFinancialSnapshot],
    *,
    as_of_date: date,
    group: ChitGroup | None = None,
) -> MembershipDuesSnapshot:
    if not installments:
        return MembershipDuesSnapshot(
            membership_id=membership_id,
            penalty_amount=0,
            payment_status="FULL",
            arrears_amount=0,
            next_due_amount=0,
            next_due_date=None,
            total_due=0,
            total_paid=0,
            outstanding_amount=0,
        )

    total_due = 0
    total_paid = 0
    penalty_amount = 0
    arrears_amount = 0
    next_due_amount = 0
    next_due_date: date | None = None
    has_partial_arrears = False
    next_cycle_amount = 0
    earliest_overdue_due_date: date | None = None
    has_due_or_paid_activity = False
    earliest_cycle_no = installments[0].cycle_no if installments else None

    for installment in installments:
        total_due += installment.total_due_amount
        total_paid += installment.paid_amount
        penalty_amount += installment.penalty_amount
        if installment.paid_amount > 0:
            has_due_or_paid_activity = True

        if installment.balance_amount <= 0:
            continue

        if installment.due_date <= as_of_date:
            has_due_or_paid_activity = True
            arrears_amount += installment.balance_amount
            if earliest_overdue_due_date is None or installment.due_date < earliest_overdue_due_date:
                earliest_overdue_due_date = installment.due_date
            if installment.paid_amount > 0:
                has_partial_arrears = True
            continue

        if next_due_date is None or installment.due_date < next_due_date:
            next_due_date = installment.due_date
            next_cycle_amount = installment.balance_amount

    if (
        not has_due_or_paid_activity
        and next_due_date is not None
        and group is not None
        and earliest_cycle_no is not None
        and int(earliest_cycle_no) > max(int(group.current_cycle_no or 1), 1)
    ):
        return MembershipDuesSnapshot(
            membership_id=membership_id,
            penalty_amount=0,
            payment_status="FULL",
            arrears_amount=0,
            next_due_amount=next_cycle_amount,
            next_due_date=next_due_date,
            total_due=0,
            total_paid=0,
            outstanding_amount=0,
        )

    if next_due_date is not None:
        next_due_amount = arrears_amount + next_cycle_amount
    elif arrears_amount > 0:
        next_due_amount = arrears_amount
        next_due_date = earliest_overdue_due_date

    if arrears_amount <= 0:
        payment_status = "FULL"
    elif has_partial_arrears:
        payment_status = "PARTIAL"
    else:
        payment_status = "PENDING"

    return MembershipDuesSnapshot(
        membership_id=membership_id,
        penalty_amount=penalty_amount,
        payment_status=payment_status,
        arrears_amount=arrears_amount,
        next_due_amount=next_due_amount,
        next_due_date=next_due_date,
        total_due=total_due,
        total_paid=total_paid,
        outstanding_amount=next_due_amount,
    )


def build_membership_dues_snapshot_map(
    db: Session,
    membership_ids: list[int],
    *,
    as_of_date: date | None = None,
) -> dict[int, MembershipDuesSnapshot]:
    unique_membership_ids = sorted(set(int(membership_id) for membership_id in membership_ids if membership_id is not None))
    if not unique_membership_ids:
        return {}

    effective_as_of_date = as_of_date or utcnow().date()
    rows = db.scalars(
        select(Installment)
        .where(Installment.membership_id.in_(unique_membership_ids))
        .order_by(Installment.membership_id.asc(), Installment.due_date.asc(), Installment.cycle_no.asc(), Installment.id.asc())
    ).all()
    group_ids = sorted({installment.group_id for installment in rows})
    groups_by_id = {
        group.id: group
        for group in db.scalars(select(ChitGroup).where(ChitGroup.id.in_(group_ids))).all()
    }

    installments_by_membership_id: dict[int, list[InstallmentFinancialSnapshot]] = {membership_id: [] for membership_id in unique_membership_ids}
    for installment in rows:
        installments_by_membership_id.setdefault(installment.membership_id, []).append(
            build_installment_financial_snapshot(
                installment,
                groups_by_id.get(installment.group_id),
                as_of_date=effective_as_of_date,
            )
        )
    membership_group_by_id = {
        membership_id: groups_by_id.get(installments[0].group_id) if installments else None
        for membership_id, installments in installments_by_membership_id.items()
    }

    return {
        membership_id: _build_membership_dues_snapshot(
            membership_id,
            installments_by_membership_id.get(membership_id, []),
            as_of_date=effective_as_of_date,
            group=membership_group_by_id.get(membership_id),
        )
        for membership_id in unique_membership_ids
    }


def apply_membership_payables_for_cycle(
    db: Session,
    *,
    group: ChitGroup,
    cycle_no: int,
    membership_payables: tuple[MembershipPayableBreakdown, ...],
) -> dict[int, Installment]:
    if not membership_payables:
        return {}

    payable_by_membership_id = {
        int(payable.membership_id): money_int(payable.member_payable_amount)
        for payable in membership_payables
    }
    membership_ids = sorted(payable_by_membership_id)
    installments = db.scalars(
        select(Installment).where(
            Installment.group_id == group.id,
            Installment.cycle_no == cycle_no,
            Installment.membership_id.in_(membership_ids),
        )
    ).all()
    installments_by_membership_id = {installment.membership_id: installment for installment in installments}
    updated_at = utcnow()

    for membership_id in membership_ids:
        installment = installments_by_membership_id.get(membership_id)
        if installment is None:
            installment = Installment(
                group_id=group.id,
                membership_id=membership_id,
                cycle_no=cycle_no,
                due_date=_calculate_due_date(group.start_date, group.cycle_frequency, cycle_no),
                due_amount=0,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=0,
                status="pending",
            )
            db.add(installment)
            installments_by_membership_id[membership_id] = installment
            paid_amount = 0
        else:
            paid_amount = money_int(installment.paid_amount)

        due_amount = payable_by_membership_id[membership_id]
        balance_amount = max(due_amount - paid_amount, 0)

        installment.due_amount = due_amount
        installment.penalty_amount = 0
        installment.balance_amount = balance_amount
        installment.updated_at = updated_at

        if balance_amount <= 0:
            installment.status = "paid"
        elif paid_amount > 0:
            installment.status = "partial"
        else:
            installment.status = "pending"

    db.flush()
    return installments_by_membership_id


def reconcile_installment_payment(
    db: Session,
    installment: Installment,
    group: ChitGroup | None,
    amount: int,
    *,
    as_of_date: date | None = None,
    commit: bool = True,
) -> Installment:
    current_paid = money_int(installment.paid_amount)
    payment_amount = money_int(amount)
    effective_as_of_date = as_of_date or utcnow().date()
    financial_snapshot = build_installment_financial_snapshot(
        installment,
        group,
        as_of_date=effective_as_of_date,
    )

    new_paid_amount = current_paid + payment_amount
    installment.penalty_amount = financial_snapshot.penalty_amount
    if new_paid_amount >= financial_snapshot.total_due_amount:
        installment.paid_amount = financial_snapshot.total_due_amount
        installment.balance_amount = 0
        installment.status = "paid"
    elif new_paid_amount > 0:
        installment.paid_amount = new_paid_amount
        installment.balance_amount = financial_snapshot.total_due_amount - new_paid_amount
        installment.status = "partial"
    else:
        installment.paid_amount = 0
        installment.balance_amount = financial_snapshot.total_due_amount
        installment.status = "pending"

    installment.last_paid_at = utcnow()
    installment.updated_at = installment.last_paid_at

    db.add(installment)
    if commit:
        db.commit()
        db.refresh(installment)
    else:
        db.flush()
    return installment


def rebuild_installment_from_payments(
    db: Session,
    installment: Installment,
    group: ChitGroup | None,
    *,
    commit: bool = True,
) -> Installment:
    payments = db.scalars(
        select(Payment)
        .where(
            Payment.installment_id == installment.id,
            Payment.status == "recorded",
        )
        .order_by(Payment.payment_date.asc(), Payment.id.asc())
    ).all()
    effective_as_of_date = max((payment.payment_date for payment in payments), default=utcnow().date())
    financial_snapshot = build_installment_financial_snapshot(
        installment,
        group,
        as_of_date=effective_as_of_date,
    )
    total_paid_amount = sum(money_int(payment.amount) for payment in payments)
    new_penalty_amount = financial_snapshot.penalty_amount
    new_paid_amount = min(total_paid_amount, financial_snapshot.total_due_amount)
    new_balance_amount = max(financial_snapshot.total_due_amount - new_paid_amount, 0)
    if new_balance_amount <= 0:
        new_status = "paid"
    elif new_paid_amount > 0:
        new_status = "partial"
    else:
        new_status = "pending"
    new_last_paid_at = installment.last_paid_at or (utcnow() if payments else None)

    if (
        money_int(installment.penalty_amount) == new_penalty_amount
        and money_int(installment.paid_amount) == new_paid_amount
        and money_int(installment.balance_amount) == new_balance_amount
        and installment.status == new_status
        and installment.last_paid_at == new_last_paid_at
    ):
        return installment

    installment.penalty_amount = new_penalty_amount
    installment.paid_amount = new_paid_amount
    installment.balance_amount = new_balance_amount
    installment.status = new_status
    installment.last_paid_at = new_last_paid_at
    installment.updated_at = utcnow()

    db.add(installment)
    if commit:
        db.commit()
        db.refresh(installment)
    else:
        db.flush()
    return installment
