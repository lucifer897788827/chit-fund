from sqlalchemy.orm import Session

from app.core.pagination import PaginatedResponse
from app.core.audit import log_audit_event
from app.core.money import money_int
from app.core.security import CurrentUser, require_owner
from app.models.money import Payment
from app.modules.notifications.service import (
    dispatch_staged_notifications,
    notify_payment_recorded,
)
from app.modules.payments.installment_service import build_membership_dues_snapshot_map, reconcile_installment_payment
from app.modules.payments.ledger_service import create_payment_ledger_entry
from app.modules.payments.queries import get_member_outstanding_totals, list_payments
from app.modules.payments.validation import validate_payment_submission


def _payment_group_id(payment: Payment, context=None) -> int | None:
    if context is not None:
        if context.membership is not None:
            return context.membership.group_id
        if context.installment is not None:
            return context.installment.group_id
    return None


def _serialize_payment(
    payment: Payment,
    *,
    group_id: int | None = None,
    installment=None,
    ledger_entry=None,
    dues_snapshot=None,
) -> dict:
    payload = {
        "id": payment.id,
        "ownerId": payment.owner_id,
        "subscriberId": payment.subscriber_id,
        "membershipId": payment.membership_id,
        "installmentId": payment.installment_id,
        "cycleNo": installment.cycle_no if installment is not None else None,
        "groupId": group_id,
        "paymentType": payment.payment_type,
        "paymentMethod": payment.payment_method,
        "amount": money_int(payment.amount),
        "paymentDate": payment.payment_date,
        "referenceNo": payment.reference_no,
        "status": payment.status,
        "installmentStatus": installment.status if installment is not None else None,
        "installmentBalanceAmount": money_int(installment.balance_amount) if installment is not None else None,
        "ledgerEntryId": ledger_entry.id if ledger_entry is not None else None,
    }
    if dues_snapshot is not None:
        payload.update(dues_snapshot.as_dict())
    return payload


def record_payment(db: Session, payload, current_user: CurrentUser):
    context = validate_payment_submission(db, payload, current_user)
    before_dues_snapshot = None
    if context.membership is not None:
        before_dues_snapshot = build_membership_dues_snapshot_map(
            db,
            [context.membership.id],
            as_of_date=payload.paymentDate,
        ).get(context.membership.id)
    installment_before = None
    if context.installment is not None:
        installment_before = {
            "installmentId": context.installment.id,
            "status": context.installment.status,
            "paidAmount": money_int(context.installment.paid_amount),
            "balanceAmount": money_int(context.installment.balance_amount),
            "penaltyAmount": money_int(context.installment.penalty_amount),
        }

    payment = Payment(
        owner_id=context.owner.id,
        subscriber_id=context.subscriber.id,
        membership_id=context.membership.id if context.membership is not None else None,
        installment_id=context.installment.id if context.installment is not None else None,
        payment_type=payload.paymentType,
        payment_method=payload.paymentMethod,
        amount=payload.amount,
        payment_date=payload.paymentDate,
        reference_no=payload.referenceNo,
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    db.add(payment)
    db.flush()

    updated_installment = None
    if context.installment is not None:
        updated_installment = reconcile_installment_payment(
            db,
            context.installment,
            context.group,
            payload.amount,
            as_of_date=payload.paymentDate,
            commit=False,
        )

    ledger_entry = create_payment_ledger_entry(db, payment)
    notify_payment_recorded(db, payment=payment)
    after_dues_snapshot = None
    if payment.membership_id is not None:
        after_dues_snapshot = build_membership_dues_snapshot_map(
            db,
            [payment.membership_id],
            as_of_date=payment.payment_date,
        ).get(payment.membership_id)
    log_audit_event(
        db,
        action="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        current_user=current_user,
        owner_id=context.owner.id,
        metadata={
            "amount": money_int(payment.amount),
            "groupId": _payment_group_id(payment, context),
            "paymentMethod": payment.payment_method,
            "paymentType": payment.payment_type,
            "subscriberId": payment.subscriber_id,
        },
        before={
            "installment": installment_before,
            "dues": before_dues_snapshot.as_dict() if before_dues_snapshot is not None else None,
        },
        after={
            "paymentId": payment.id,
            "installment": (
                {
                    "installmentId": updated_installment.id,
                    "status": updated_installment.status,
                    "paidAmount": money_int(updated_installment.paid_amount),
                    "balanceAmount": money_int(updated_installment.balance_amount),
                    "penaltyAmount": money_int(updated_installment.penalty_amount),
                }
                if updated_installment is not None
                else None
            ),
            "dues": after_dues_snapshot.as_dict() if after_dues_snapshot is not None else None,
        },
    )
    db.commit()
    db.refresh(payment)
    if updated_installment is not None:
        db.refresh(updated_installment)
    db.refresh(ledger_entry)
    dispatch_staged_notifications(db)
    dues_snapshot = None
    if payment.membership_id is not None:
        dues_snapshot = build_membership_dues_snapshot_map(
            db,
            [payment.membership_id],
            as_of_date=payment.payment_date,
        ).get(payment.membership_id)

    return _serialize_payment(
        payment,
        group_id=_payment_group_id(payment, context),
        installment=updated_installment,
        ledger_entry=ledger_entry,
        dues_snapshot=dues_snapshot,
    )


def list_payment_history(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    require_owner(current_user)
    return list_payments(
        db,
        current_user,
        subscriber_id=subscriber_id,
        group_id=group_id,
        page=page,
        page_size=page_size,
    )


def list_member_balances(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    require_owner(current_user)
    return get_member_outstanding_totals(
        db,
        current_user,
        subscriber_id=subscriber_id,
        group_id=group_id,
        page=page,
        page_size=page_size,
    )
