from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payment
from app.models.user import Owner, Subscriber, User
from app.modules.payments.schemas import PaymentCreate
from app.modules.payments.validation import validate_payment_submission


def _owner_current_user(db_session, phone: str = "9999999999") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _make_group(db_session, *, owner_id: int, group_code: str, installment_amount: float = 1000.0) -> ChitGroup:
    group = ChitGroup(
        owner_id=owner_id,
        group_code=group_code,
        title=f"{group_code} Title",
        chit_value=10000,
        installment_amount=installment_amount,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    return group


def _make_membership(db_session, *, group_id: int, subscriber_id: int, member_no: int) -> GroupMembership:
    membership = GroupMembership(
        group_id=group_id,
        subscriber_id=subscriber_id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    return membership


def _make_installment(
    db_session,
    *,
    group_id: int,
    membership_id: int,
    cycle_no: int,
    due_amount: float,
    penalty_amount: float = 0.0,
    paid_amount: float = 0.0,
    balance_amount: float | None = None,
) -> Installment:
    installment = Installment(
        group_id=group_id,
        membership_id=membership_id,
        cycle_no=cycle_no,
        due_date=date(2026, 6, 1),
        due_amount=due_amount,
        penalty_amount=penalty_amount,
        paid_amount=paid_amount,
        balance_amount=due_amount if balance_amount is None else balance_amount,
        status="partial" if paid_amount else "pending",
    )
    db_session.add(installment)
    db_session.flush()
    return installment


def test_validate_payment_rejects_owner_mismatch(app, db_session):
    current_user = _owner_current_user(db_session)
    payload = PaymentCreate(
        ownerId=current_user.owner.id + 1,
        subscriberId=2,
        membershipId=None,
        installmentId=None,
        paymentType="installment",
        paymentMethod="upi",
        amount=25000,
        paymentDate=date(2026, 5, 10),
        referenceNo="UPI-001",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 403


def test_validate_payment_rejects_membership_subscriber_mismatch(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-001")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=current_user.subscriber.id,
        membershipId=membership.id,
        installmentId=None,
        paymentType="installment",
        paymentMethod="upi",
        amount=1000,
        paymentDate=date(2026, 5, 10),
        referenceNo="UPI-002",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 400


def test_validate_payment_rejects_invalid_installment_target_combination(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-002")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    installment = _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_amount=1000,
        balance_amount=1000,
    )

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=None,
        installmentId=installment.id,
        paymentType="installment",
        paymentMethod="upi",
        amount=1000,
        paymentDate=date(2026, 5, 10),
        referenceNo="UPI-003",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 400


def test_validate_payment_rejects_overpayment_for_installment(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-003")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    installment = _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_amount=1000,
        paid_amount=400,
        balance_amount=600,
    )

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=installment.id,
        paymentType="installment",
        paymentMethod="upi",
        amount=700,
        paymentDate=date(2026, 5, 10),
        referenceNo="UPI-004",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 400


def test_validate_payment_resolves_next_unpaid_installment_from_membership(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-003A")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    first_installment = _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_amount=1000,
        paid_amount=400,
        balance_amount=600,
    )
    _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=2,
        due_amount=1000,
        paid_amount=0,
        balance_amount=1000,
    )

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=None,
        cycleNo=None,
        paymentType="installment",
        paymentMethod="upi",
        amount=500,
        paymentDate=date(2026, 5, 10),
        referenceNo="UPI-004A",
    )

    context = validate_payment_submission(db_session, payload, current_user)

    assert context.membership is not None
    assert context.membership.id == membership.id
    assert context.installment is not None
    assert context.installment.id == first_installment.id


def test_validate_payment_resolves_installment_by_cycle_when_cycle_no_is_supplied(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-003B")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_amount=1000,
        paid_amount=1000,
        balance_amount=0,
    )
    second_installment = _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=2,
        due_amount=1000,
        paid_amount=0,
        balance_amount=1000,
    )

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=None,
        cycleNo=2,
        paymentType="installment",
        paymentMethod="upi",
        amount=750,
        paymentDate=date(2026, 6, 10),
        referenceNo="UPI-004B",
    )

    context = validate_payment_submission(db_session, payload, current_user)

    assert context.installment is not None
    assert context.installment.id == second_installment.id


def test_validate_payment_rejects_exact_duplicate_submission(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-004")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    installment = _make_installment(
        db_session,
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_amount=1000,
        balance_amount=1000,
    )

    existing_payment = Payment(
        owner_id=current_user.owner.id,
        subscriber_id=subscriber.id,
        membership_id=membership.id,
        installment_id=installment.id,
        payment_type="installment",
        payment_method="upi",
        amount=1000,
        payment_date=date(2026, 5, 10),
        reference_no=None,
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    db_session.add(existing_payment)
    db_session.commit()

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=installment.id,
        paymentType="installment",
        paymentMethod="upi",
        amount=1000,
        paymentDate=date(2026, 5, 10),
        referenceNo=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 409


def test_validate_payment_rejects_non_positive_amount(app, db_session):
    current_user = _owner_current_user(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=current_user.owner.id, group_code="PAY-VAL-005")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)

    payload = PaymentCreate(
        ownerId=current_user.owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=None,
        paymentType="membership",
        paymentMethod="cash",
        amount=1,
        paymentDate=date(2026, 5, 10),
        referenceNo=None,
    )

    payload.amount = 0

    with pytest.raises(HTTPException) as exc_info:
        validate_payment_submission(db_session, payload, current_user)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Payment amount must be greater than zero"
