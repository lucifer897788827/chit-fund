from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment, MembershipSlot
from app.models.money import Payment, Payout
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.service import create_auction_result
from app.modules.payments.queries import get_member_outstanding_totals, list_payments, list_payouts


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


def _make_subscriber_with_user(
    db_session,
    *,
    owner_id: int,
    phone: str,
    email: str,
    full_name: str,
) -> Subscriber:
    user = User(
        email=email,
        phone=phone,
        password_hash="not-used",
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner_id,
        full_name=full_name,
        phone=phone,
        email=email,
        status="active",
    )
    db_session.add(subscriber)
    db_session.flush()
    return subscriber


def test_list_payments_filters_by_subscriber_and_group_for_owner(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group_one = _make_group(db_session, owner_id=owner.id, group_code="PAY-001")
    group_two = _make_group(db_session, owner_id=owner.id, group_code="PAY-002")
    other_owner_group = _make_group(db_session, owner_id=owner.id + 1, group_code="PAY-999")

    membership_one = _make_membership(db_session, group_id=group_one.id, subscriber_id=subscriber.id, member_no=1)
    membership_two = _make_membership(db_session, group_id=group_two.id, subscriber_id=subscriber.id, member_no=2)
    other_membership = _make_membership(
        db_session,
        group_id=other_owner_group.id,
        subscriber_id=subscriber.id,
        member_no=3,
    )

    first_payment = Payment(
        owner_id=owner.id,
        subscriber_id=subscriber.id,
        membership_id=membership_one.id,
        installment_id=None,
        payment_type="installment",
        payment_method="upi",
        amount=1200,
        payment_date=date(2026, 5, 10),
        reference_no="PAY-001",
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    second_payment = Payment(
        owner_id=owner.id,
        subscriber_id=subscriber.id,
        membership_id=membership_two.id,
        installment_id=None,
        payment_type="installment",
        payment_method="cash",
        amount=900,
        payment_date=date(2026, 5, 11),
        reference_no="PAY-002",
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    other_payment = Payment(
        owner_id=owner.id + 1,
        subscriber_id=subscriber.id,
        membership_id=other_membership.id,
        installment_id=None,
        payment_type="installment",
        payment_method="cash",
        amount=700,
        payment_date=date(2026, 5, 12),
        reference_no="PAY-999",
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    db_session.add_all([first_payment, second_payment, other_payment])
    db_session.commit()

    results = list_payments(
        db_session,
        current_user,
        subscriber_id=subscriber.id,
        group_id=group_one.id,
    )

    assert results == [
        {
            "id": first_payment.id,
            "ownerId": owner.id,
            "subscriberId": subscriber.id,
            "membershipId": membership_one.id,
            "installmentId": None,
            "cycleNo": None,
            "groupId": group_one.id,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 1200.0,
            "paymentDate": date(2026, 5, 10),
            "referenceNo": "PAY-001",
            "status": "recorded",
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 0.0,
            "nextDueDate": None,
            "totalDue": 0.0,
            "totalPaid": 0.0,
            "outstandingAmount": 0.0,
        }
    ]


def test_get_member_outstanding_totals_groups_installment_balances_by_member(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=owner.id, group_code="BAL-001")
    other_group = _make_group(db_session, owner_id=owner.id + 1, group_code="BAL-999")

    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    other_membership = _make_membership(
        db_session,
        group_id=other_group.id,
        subscriber_id=subscriber.id,
        member_no=2,
    )
    db_session.add_all(
        [
            MembershipSlot(user_id=subscriber.user_id, group_id=group.id, slot_number=1, has_won=True),
            MembershipSlot(user_id=subscriber.user_id, group_id=group.id, slot_number=2, has_won=False),
            MembershipSlot(user_id=subscriber.user_id, group_id=group.id, slot_number=3, has_won=False),
        ]
    )

    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 5, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=400,
                balance_amount=600,
                status="partial",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 6, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=200,
                balance_amount=800,
                status="partial",
            ),
            Installment(
                group_id=other_group.id,
                membership_id=other_membership.id,
                cycle_no=1,
                due_date=date(2026, 5, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=1000,
                balance_amount=0,
                status="paid",
            ),
        ]
    )
    db_session.commit()

    results = get_member_outstanding_totals(
        db_session,
        current_user,
        group_id=group.id,
        subscriber_id=subscriber.id,
    )

    assert results == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "memberNo": 1,
            "slotCount": 3,
            "wonSlotCount": 1,
            "remainingSlotCount": 2,
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 600.0,
            "nextDueDate": date(2026, 5, 1),
            "totalDue": 2000.0,
            "totalPaid": 600.0,
            "outstandingAmount": 600.0,
        }
    ]


def test_get_member_outstanding_totals_keeps_fresh_future_only_memberships_at_zero_due(app, db_session, monkeypatch):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=owner.id, group_code="BAL-FRESH-001")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=3,
                due_date=date(2026, 7, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=1000,
                status="pending",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=4,
                due_date=date(2026, 8, 1),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=1000,
                status="pending",
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc))

    results = get_member_outstanding_totals(
        db_session,
        current_user,
        group_id=group.id,
        subscriber_id=subscriber.id,
    )

    assert results == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "memberNo": 1,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 1000.0,
            "nextDueDate": date(2026, 7, 1),
            "totalDue": 0.0,
            "totalPaid": 0.0,
            "outstandingAmount": 0.0,
        }
    ]


def test_get_member_outstanding_totals_reflects_finalized_auction_member_payable_amount(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    owner_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "9999999999"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert owner_subscriber is not None
    assert subscriber is not None

    third_subscriber = _make_subscriber_with_user(
        db_session,
        owner_id=owner.id,
        phone="8777777771",
        email="member-three@example.com",
        full_name="Member Three",
    )
    fourth_subscriber = _make_subscriber_with_user(
        db_session,
        owner_id=owner.id,
        phone="8777777772",
        email="member-four@example.com",
        full_name="Member Four",
    )

    group = ChitGroup(
        owner_id=owner.id,
        group_code="BAL-AUC-001",
        title="Auction Payable Balances",
        chit_value=100000,
        installment_amount=10000,
        member_count=4,
        cycle_count=1,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    memberships = [
        _make_membership(db_session, group_id=group.id, subscriber_id=owner_subscriber.id, member_no=1),
        _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=2),
        _make_membership(db_session, group_id=group.id, subscriber_id=third_subscriber.id, member_no=3),
        _make_membership(db_session, group_id=group.id, subscriber_id=fourth_subscriber.id, member_no=4),
    ]
    users = {
        owner_subscriber.id: db_session.scalar(select(User).where(User.id == owner.user_id)),
        subscriber.id: db_session.scalar(select(User).where(User.id == subscriber.user_id)),
        third_subscriber.id: db_session.scalar(select(User).where(User.id == third_subscriber.user_id)),
        fourth_subscriber.id: db_session.scalar(select(User).where(User.id == fourth_subscriber.user_id)),
    }
    db_session.add_all(
        [
            MembershipSlot(user_id=users[owner_subscriber.id].id, group_id=group.id, slot_number=1, has_won=False),
            MembershipSlot(user_id=users[subscriber.id].id, group_id=group.id, slot_number=2, has_won=False),
            MembershipSlot(user_id=users[third_subscriber.id].id, group_id=group.id, slot_number=3, has_won=False),
            MembershipSlot(user_id=users[fourth_subscriber.id].id, group_id=group.id, slot_number=4, has_won=False),
        ]
    )
    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 1),
                due_amount=10000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=10000,
                status="pending",
            )
            for membership in memberships
        ]
    )

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 4, 10, 10, 5, tzinfo=timezone.utc),
        commission_mode="FIXED_AMOUNT",
        commission_value=2000,
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=memberships[0].id,
        bidder_user_id=owner.user_id,
        idempotency_key="balance-auction-win",
        bid_amount=20000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 4, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=owner.user_id)

    assert result is not None
    assert float(result.owner_commission_amount) == 2000.0
    assert float(result.dividend_per_member_amount) == 4500.0
    assert float(result.winner_payout_amount) == 74500.0

    results = get_member_outstanding_totals(
        db_session,
        current_user,
        group_id=group.id,
        subscriber_id=subscriber.id,
    )

    assert results == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": memberships[1].id,
            "memberNo": 2,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
            "paymentStatus": "PENDING",
            "arrearsAmount": 5500.0,
            "nextDueAmount": 5500.0,
            "nextDueDate": date(2026, 4, 1),
            "totalDue": 5500.0,
            "totalPaid": 0.0,
            "outstandingAmount": 5500.0,
        }
    ]


def test_list_payments_uses_installment_group_when_membership_is_missing(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=owner.id, group_code="PAY-INT-001")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    installment = Installment(
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_date=date(2026, 5, 1),
        due_amount=1000,
        penalty_amount=0,
        paid_amount=250,
        balance_amount=750,
        status="partial",
    )
    db_session.add(installment)
    db_session.flush()

    payment = Payment(
        owner_id=owner.id,
        subscriber_id=subscriber.id,
        membership_id=None,
        installment_id=installment.id,
        payment_type="installment",
        payment_method="upi",
        amount=250,
        payment_date=date(2026, 5, 2),
        reference_no="PAY-INT-001",
        recorded_by_user_id=current_user.user.id,
        status="recorded",
    )
    db_session.add(payment)
    db_session.commit()

    results = list_payments(
        db_session,
        current_user,
        subscriber_id=subscriber.id,
        group_id=group.id,
    )

    assert results == [
        {
            "id": payment.id,
            "ownerId": owner.id,
            "subscriberId": subscriber.id,
            "membershipId": None,
            "installmentId": installment.id,
            "cycleNo": installment.cycle_no,
            "groupId": group.id,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 250.0,
            "paymentDate": date(2026, 5, 2),
            "referenceNo": "PAY-INT-001",
            "status": "recorded",
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 750.0,
            "nextDueDate": date(2026, 5, 1),
            "totalDue": 1000.0,
            "totalPaid": 250.0,
            "outstandingAmount": 750.0,
        }
    ]


def test_list_payouts_returns_owner_payout_summary(app, db_session):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=owner.id, group_code="PAYOUT-001")
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        actual_end_at=None,
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="PAYOUT-Q-001",
        bid_amount=3000,
        bid_discount_amount=500,
        placed_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()

    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=1,
        winner_membership_id=membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=3000,
        dividend_pool_amount=500,
        dividend_per_member_amount=50,
        owner_commission_amount=100,
        winner_payout_amount=9500,
        finalized_by_user_id=owner.user_id,
    )
    db_session.add(result)
    db_session.flush()

    payout = Payout(
        owner_id=owner.id,
        auction_result_id=result.id,
        subscriber_id=subscriber.id,
        membership_id=membership.id,
        gross_amount=10000,
        deductions_amount=500,
        net_amount=9500,
        payout_method="upi",
        payout_date=date(2026, 5, 11),
        reference_no="PAYOUT-Q-001",
        status="paid",
    )
    db_session.add(payout)
    db_session.commit()

    results = list_payouts(
        db_session,
        current_user,
        subscriber_id=subscriber.id,
        group_id=group.id,
    )

    assert results == [
        {
            "id": payout.id,
            "ownerId": owner.id,
            "auctionResultId": result.id,
            "groupId": group.id,
            "groupCode": "PAYOUT-001",
            "groupTitle": "PAYOUT-001 Title",
            "subscriberId": subscriber.id,
            "subscriberName": subscriber.full_name,
            "membershipId": membership.id,
            "memberNo": 1,
            "cycleNo": 1,
            "grossAmount": 10000.0,
            "deductionsAmount": 500.0,
            "netAmount": 9500.0,
            "payoutMethod": "upi",
            "payoutDate": date(2026, 5, 11),
            "referenceNo": "PAYOUT-Q-001",
            "status": "paid",
            "createdAt": payout.created_at,
            "paymentStatus": "FULL",
            "arrearsAmount": 0.0,
            "nextDueAmount": 0.0,
            "nextDueDate": None,
            "totalDue": 0.0,
            "totalPaid": 0.0,
            "outstandingAmount": 0.0,
        }
    ]

    alias_results = list_payouts(
        db_session,
        current_user,
        subscriber_id=subscriber.id,
        group_id=group.id,
        status="completed",
    )

    assert [item["id"] for item in alias_results] == [payout.id]


def test_get_member_outstanding_totals_includes_penalty_amount_when_enabled(app, db_session, monkeypatch):
    current_user = _owner_current_user(db_session)
    owner = current_user.owner
    assert owner is not None

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = _make_group(db_session, owner_id=owner.id, group_code="BAL-PEN-001", installment_amount=1000.0)
    group.penalty_enabled = True
    group.penalty_type = "FIXED"
    group.penalty_value = 250
    group.grace_period_days = 1
    membership = _make_membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    db_session.add(
        Installment(
            group_id=group.id,
            membership_id=membership.id,
            cycle_no=1,
            due_date=date(2026, 5, 1),
            due_amount=1000,
            penalty_amount=0,
            paid_amount=0,
            balance_amount=1000,
            status="pending",
        )
    )
    db_session.commit()

    monkeypatch.setattr("app.modules.payments.installment_service.utcnow", lambda: datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc))
    results = get_member_outstanding_totals(
        db_session,
        current_user,
        group_id=group.id,
        subscriber_id=subscriber.id,
    )

    assert results == [
        {
            "groupId": group.id,
            "subscriberId": subscriber.id,
            "membershipId": membership.id,
            "memberNo": 1,
            "slotCount": 1,
            "wonSlotCount": 0,
            "remainingSlotCount": 1,
            "paymentStatus": "PENDING",
            "penaltyAmount": 250.0,
            "arrearsAmount": 1250.0,
            "nextDueAmount": 1250.0,
            "nextDueDate": date(2026, 5, 1),
            "totalDue": 1250.0,
            "totalPaid": 0.0,
            "outstandingAmount": 1250.0,
        }
    ]
