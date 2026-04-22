from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Subscriber, User
from app.modules.auctions.service import create_auction_result, select_winning_bid
from app.modules.payments.auction_payout_engine import calculate_payout


def _seed_auction_session(
    db_session,
    *,
    commission_mode: str = "NONE",
    commission_value: float | None = None,
):
    group = ChitGroup(
        owner_id=1,
        group_code="AUC-RESULT-001",
        title="Auction Result Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=date(2026, 7, 1),
        first_auction_date=date(2026, 7, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=1,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
        commission_mode=commission_mode,
        commission_value=commission_value,
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(membership)
    return session, membership, group


def _create_group_member(db_session, group_id: int, *, suffix: str, member_no: int):
    user = User(
        email=f"member-{suffix}@example.com",
        phone=f"700000000{suffix}",
        password_hash="not-used",
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=1,
        full_name=f"Member {suffix}",
        phone=user.phone,
        email=user.email,
        status="active",
    )
    db_session.add(subscriber)
    db_session.flush()

    membership = GroupMembership(
        group_id=group_id,
        subscriber_id=subscriber.id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    return user, membership


def test_select_winning_bid_prefers_highest_amount_then_earliest_placed_at_then_lowest_id(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    user_two, membership_two = _create_group_member(db_session, group.id, suffix="1", member_no=2)
    user_three, membership_three = _create_group_member(db_session, group.id, suffix="2", member_no=3)

    lower_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="lower",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 30, tzinfo=timezone.utc),
        is_valid=True,
    )
    tied_earlier_lower_id_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="tie-earlier-lower-id",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 30, tzinfo=timezone.utc),
        is_valid=True,
    )
    tied_later_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership_two.id,
        bidder_user_id=user_two.id,
        idempotency_key="tie-later",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([lower_bid, tied_earlier_lower_id_bid, tied_later_bid])
    db_session.flush()

    tied_earlier_higher_id_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership_three.id,
        bidder_user_id=user_three.id,
        idempotency_key="tie-earlier-higher-id",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 30, tzinfo=timezone.utc),
        is_valid=True,
    )
    invalid_highest_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership_two.id,
        bidder_user_id=user_two.id,
        idempotency_key="invalid-highest",
        bid_amount=16000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 5, tzinfo=timezone.utc),
        is_valid=False,
        invalid_reason="ignored",
    )
    db_session.add_all([tied_earlier_higher_id_bid, invalid_highest_bid])
    db_session.commit()

    winning_bid = select_winning_bid(db_session, session.id)

    assert winning_bid is not None
    assert winning_bid.id == tied_earlier_lower_id_bid.id


def test_create_auction_result_persists_winner_and_amounts(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="winner",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    assert result.auction_session_id == session.id
    assert result.group_id == group.id
    assert result.cycle_no == session.cycle_no
    assert result.winner_membership_id == membership.id
    assert result.winning_bid_id == winning_bid.id
    assert float(result.winning_bid_amount) == 10000.0
    assert float(result.owner_commission_amount) == 0.0
    assert float(result.dividend_pool_amount) == 10000.0
    assert float(result.dividend_per_member_amount) == 500.0
    assert float(result.winner_payout_amount) == 180500.0

    db_session.refresh(session)
    assert session.winning_bid_id == winning_bid.id

    stored_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    assert stored_result is not None
    assert stored_result.id == result.id


def test_create_auction_result_marks_winner_unavailable_for_future_bids(app, db_session):
    session, winner_membership, group = _seed_auction_session(db_session)
    other_user, other_membership = _create_group_member(db_session, group.id, suffix="1", member_no=2)

    losing_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=winner_membership.id,
        bidder_user_id=1,
        idempotency_key="loser",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=other_membership.id,
        bidder_user_id=other_user.id,
        idempotency_key="winner",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 20, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([losing_bid, winning_bid])
    db_session.commit()
    db_session.refresh(losing_bid)
    db_session.refresh(winning_bid)

    create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    db_session.refresh(winner_membership)
    db_session.refresh(other_membership)

    assert winner_membership.prized_status == "unprized"
    assert winner_membership.prized_cycle_no is None
    assert winner_membership.can_bid is True
    assert other_membership.prized_status == "prized"
    assert other_membership.prized_cycle_no == session.cycle_no
    assert other_membership.can_bid is False


def test_create_auction_result_returns_none_when_no_valid_bids_exist(app, db_session):
    session, membership, _group = _seed_auction_session(db_session)
    invalid_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="invalid-only",
        bid_amount=7000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=False,
        invalid_reason="not-eligible",
    )
    db_session.add(invalid_bid)
    db_session.commit()

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is None
    db_session.refresh(session)
    assert session.winning_bid_id is None
    assert db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id)) is None


def test_create_auction_result_advances_group_to_next_cycle_when_more_cycles_remain(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="advance-cycle",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    db_session.refresh(group)
    assert group.current_cycle_no == 2
    assert group.bidding_enabled is True
    assert group.status == "active"


def test_create_auction_result_marks_group_completed_on_final_cycle(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    group.cycle_count = 1
    db_session.commit()
    db_session.refresh(group)

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="complete-cycle",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    db_session.refresh(group)
    assert group.current_cycle_no == 1
    assert group.bidding_enabled is False
    assert group.status == "completed"


def test_create_auction_result_applies_percentage_commission(app, db_session):
    session, membership, _group = _seed_auction_session(
        db_session,
        commission_mode="PERCENTAGE",
        commission_value=10,
    )
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="percentage-commission",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    assert float(result.owner_commission_amount) == 1000.0
    assert float(result.dividend_pool_amount) == 9000.0
    assert float(result.dividend_per_member_amount) == 450.0
    assert float(result.winner_payout_amount) == 180450.0


def test_create_auction_result_applies_fixed_commission(app, db_session):
    session, membership, _group = _seed_auction_session(
        db_session,
        commission_mode="FIXED_AMOUNT",
        commission_value=2500,
    )
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="fixed-commission",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    assert float(result.owner_commission_amount) == 2500.0
    assert float(result.dividend_pool_amount) == 7500.0
    assert float(result.dividend_per_member_amount) == 375.0
    assert float(result.winner_payout_amount) == 180375.0


def test_create_auction_result_applies_first_month_commission(app, db_session):
    session, membership, group = _seed_auction_session(
        db_session,
        commission_mode="FIRST_MONTH",
    )
    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="first-month-commission",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()

    result = create_auction_result(db_session, session_id=session.id, finalized_by_user_id=1)

    assert result is not None
    assert float(result.owner_commission_amount) == float(group.installment_amount)
    assert float(result.dividend_pool_amount) == 0.0
    assert float(result.dividend_per_member_amount) == 0.0
    assert float(result.winner_payout_amount) == 180000.0


def test_calculate_payout_returns_slot_based_member_payables(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    db_session.add_all(
        [
            MembershipSlot(user_id=1, group_id=group.id, slot_number=1, has_won=False),
            MembershipSlot(user_id=1, group_id=group.id, slot_number=2, has_won=False),
            MembershipSlot(user_id=1, group_id=group.id, slot_number=3, has_won=False),
        ]
    )
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="multi-slot-breakdown",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.flush()

    calculation = calculate_payout(
        db_session,
        session=session,
        group=group,
        winning_bid=winning_bid,
        winner_membership_id=membership.id,
    )

    assert calculation.total_slots == 20
    assert float(calculation.dividend_per_member_amount) == 500.0
    assert calculation.winner_slot_count == 3
    assert float(calculation.winner_member_payable_amount) == 28500.0
    assert len(calculation.membership_payables) == 1
    assert calculation.membership_payables[0].slot_count == 3
    assert float(calculation.membership_payables[0].member_payable_amount) == 28500.0


def test_calculate_payout_uses_integer_slot_shares_and_tracks_organizer_remainder(app, db_session):
    session, membership, group = _seed_auction_session(db_session)
    group.member_count = 4
    group.chit_value = 100000
    group.installment_amount = 10000
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="integer-rounding",
        bid_amount=10001,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.flush()

    calculation = calculate_payout(
        db_session,
        session=session,
        group=group,
        winning_bid=winning_bid,
        winner_membership_id=membership.id,
    )

    assert calculation.total_slots == 4
    assert float(calculation.net_bid_amount) == 10001.0
    assert float(calculation.dividend_per_member_amount) == 2500.0
    assert float(calculation.rounding_adjustment_amount) == 1.0
    assert (
        calculation.dividend_per_member_amount * Decimal(calculation.total_slots)
    ) + calculation.rounding_adjustment_amount == calculation.net_bid_amount
    assert float(calculation.winner_payout_amount) == 82499.0
    assert float(calculation.winner_member_payable_amount) == 7500.0
