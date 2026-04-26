from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.security import CurrentUser, require_owner
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payment
from app.models.user import Owner, Subscriber
from app.modules.payments.installment_service import build_installment_financial_snapshot

PAYOUT_STATUS_PENDING = "pending"
PAYOUT_STATUS_PAID = "paid"
PAYOUT_STATUS_ALIASES = {
    "created": PAYOUT_STATUS_PENDING,
    "recorded": PAYOUT_STATUS_PENDING,
    "pending": PAYOUT_STATUS_PENDING,
    "processing": PAYOUT_STATUS_PENDING,
    "processed": PAYOUT_STATUS_PENDING,
    "paid": PAYOUT_STATUS_PAID,
    "completed": PAYOUT_STATUS_PAID,
    "settled": PAYOUT_STATUS_PAID,
}
PAYOUT_STATUS_FILTER_VALUES = frozenset(PAYOUT_STATUS_ALIASES) | {
    PAYOUT_STATUS_PENDING,
    PAYOUT_STATUS_PAID,
}


@dataclass(slots=True)
class ValidatedPaymentContext:
    owner: Owner
    group: ChitGroup | None
    subscriber: Subscriber
    membership: GroupMembership | None
    installment: Installment | None


def _resolve_installment_target(
    db: Session,
    *,
    owner_id: int,
    membership: GroupMembership,
    installment_id: int | None,
    cycle_no: int | None,
    payment_date,
) -> Installment:
    installment_statement = (
        select(Installment)
        .join(GroupMembership, GroupMembership.id == Installment.membership_id)
        .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
        .where(
            GroupMembership.id == membership.id,
            ChitGroup.owner_id == owner_id,
        )
        .with_for_update()
    )
    if installment_id is not None:
        installment = db.scalar(installment_statement.where(Installment.id == installment_id))
        if installment is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment does not belong to this membership",
            )
        return installment

    if cycle_no is not None:
        installment = db.scalar(installment_statement.where(Installment.cycle_no == cycle_no))
        if installment is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment cycle does not belong to this membership",
            )
        return installment

    installments = db.scalars(
        installment_statement.order_by(
            Installment.due_date.asc(),
            Installment.cycle_no.asc(),
            Installment.id.asc(),
        )
    ).all()
    if not installments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Installment payments require an installment for this membership",
        )

    group = db.get(ChitGroup, membership.group_id)
    for installment in installments:
        installment_snapshot = build_installment_financial_snapshot(
            installment,
            group,
            as_of_date=payment_date,
        )
        if installment_snapshot.balance_amount > 0:
            return installment

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No unpaid installment is available for this membership",
    )


def normalize_payout_status(status_value: str | None) -> str:
    if status_value is None:
        return PAYOUT_STATUS_PENDING
    normalized_status = status_value.strip().lower()
    if not normalized_status:
        return PAYOUT_STATUS_PENDING
    return PAYOUT_STATUS_ALIASES.get(normalized_status, PAYOUT_STATUS_PENDING)


def payout_status_filter_values(status_value: str | None) -> tuple[str, ...]:
    normalized_input = (status_value or "").strip().lower()
    if normalized_input not in PAYOUT_STATUS_FILTER_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported payout status filter",
        )
    normalized_status = normalize_payout_status(status_value)
    matching_statuses = {
        raw_status
        for raw_status, canonical_status in PAYOUT_STATUS_ALIASES.items()
        if canonical_status == normalized_status
    }
    matching_statuses.add(normalized_status)
    return tuple(sorted(matching_statuses))


def is_settled_payout_status(status_value: str | None) -> bool:
    return normalize_payout_status(status_value) == PAYOUT_STATUS_PAID


def validate_payment_submission(db: Session, payload, current_user: CurrentUser) -> ValidatedPaymentContext:
    owner = require_owner(current_user)
    if payload.ownerId != owner.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot record payments for another owner",
        )
    if payload.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount must be greater than zero",
        )

    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == payload.subscriberId))
    if subscriber is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscriber does not belong to this owner",
        )

    membership = None
    group = None
    if payload.membershipId is not None:
        membership = db.scalar(
            select(GroupMembership)
            .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
            .where(
                GroupMembership.id == payload.membershipId,
                ChitGroup.owner_id == owner.id,
            )
            .with_for_update()
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Membership does not belong to this owner",
            )
        if membership.subscriber_id != subscriber.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Membership does not match subscriber",
            )
        group = db.get(ChitGroup, membership.group_id)
    elif subscriber.owner_id != owner.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscriber does not belong to this owner",
        )

    cycle_no = getattr(payload, "cycleNo", None)
    installment = None
    if payload.installmentId is not None:
        if payload.paymentType != "installment":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment payments require installment payment type",
            )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installments require a membership",
            )
        installment = db.scalar(
            select(Installment)
            .join(GroupMembership, GroupMembership.id == Installment.membership_id)
            .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
            .where(
                Installment.id == payload.installmentId,
                ChitGroup.owner_id == owner.id,
            )
            .with_for_update()
        )
        if installment is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment does not belong to this owner",
            )
        if installment.membership_id != membership.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment does not match membership",
            )
        if membership.subscriber_id != subscriber.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Membership does not match subscriber",
            )
        if group is None:
            group = db.get(ChitGroup, installment.group_id)
    elif membership is not None and cycle_no is not None:
        installment = _resolve_installment_target(
            db,
            owner_id=owner.id,
            membership=membership,
            installment_id=None,
            cycle_no=cycle_no,
            payment_date=payload.paymentDate,
        )
        if group is None:
            group = db.get(ChitGroup, installment.group_id)
    elif payload.paymentType == "installment":
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment payments require a membership",
            )
        installment = _resolve_installment_target(
            db,
            owner_id=owner.id,
            membership=membership,
            installment_id=None,
            cycle_no=cycle_no,
            payment_date=payload.paymentDate,
        )
        if group is None:
            group = db.get(ChitGroup, installment.group_id)

    duplicate_conditions = [
        Payment.owner_id == owner.id,
        Payment.subscriber_id == payload.subscriberId,
    ]
    if payload.membershipId is None:
        duplicate_conditions.append(Payment.membership_id.is_(None))
    else:
        duplicate_conditions.append(Payment.membership_id == payload.membershipId)

    effective_installment_id = installment.id if installment is not None else payload.installmentId

    if effective_installment_id is None:
        duplicate_conditions.append(Payment.installment_id.is_(None))
    else:
        duplicate_conditions.append(Payment.installment_id == effective_installment_id)

    duplicate_conditions.extend(
        [
            Payment.payment_type == payload.paymentType,
            Payment.payment_method == payload.paymentMethod,
            Payment.amount == money_int(payload.amount),
            Payment.payment_date == payload.paymentDate,
        ]
    )

    if payload.referenceNo is None:
        duplicate_conditions.append(Payment.reference_no.is_(None))
    else:
        duplicate_conditions.append(Payment.reference_no == payload.referenceNo)

    duplicate_payment = db.scalar(select(Payment.id).where(*duplicate_conditions))
    if duplicate_payment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate payment submission",
        )

    if installment is not None:
        payment_amount = money_int(payload.amount)
        installment_snapshot = build_installment_financial_snapshot(
            installment,
            group,
            as_of_date=payload.paymentDate,
        )
        if payment_amount > installment_snapshot.balance_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment exceeds installment balance",
            )

    return ValidatedPaymentContext(
        owner=owner,
        group=group,
        subscriber=subscriber,
        membership=membership,
        installment=installment,
    )
