from datetime import datetime, timezone

from fastapi import HTTPException
import pytest
from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import LedgerEntry, Payout
from app.models.user import Subscriber
from app.modules.payments.payout_service import ensure_auction_payout


def _seed_payout_result(db_session, *, owner_id: int = 1):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner_id,
        group_code="PAY-PAYOUT-001",
        title="Payout Group",
        chit_value=200000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
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
        subscriber_id=subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="prized",
        can_bid=False,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="finalized",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="winner-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()

    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=session.cycle_no,
        winner_membership_id=membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=12000,
        dividend_pool_amount=0,
        dividend_per_member_amount=0,
        owner_commission_amount=0,
        winner_payout_amount=188000,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.commit()

    return group, membership, session, result


def test_ensure_auction_payout_normalizes_legacy_status(app, db_session):
    group, membership, _session, result = _seed_payout_result(db_session)
    payout = Payout(
        owner_id=group.owner_id,
        auction_result_id=result.id,
        subscriber_id=membership.subscriber_id,
        membership_id=membership.id,
        gross_amount=group.chit_value,
        deductions_amount=12000,
        net_amount=188000,
        payout_method="auction_settlement",
        payout_date=datetime(2026, 5, 10, tzinfo=timezone.utc).date(),
        reference_no=None,
        status="recorded",
    )
    db_session.add(payout)
    db_session.commit()

    settled_payout, ledger_entry = ensure_auction_payout(db_session, result=result)

    assert settled_payout.id == payout.id
    assert settled_payout.status == "pending"
    assert ledger_entry.owner_id == group.owner_id
    assert ledger_entry.source_table == "payouts"
    assert ledger_entry.source_id == payout.id


def test_ensure_auction_payout_rejects_settled_payout(app, db_session):
    group, membership, _session, result = _seed_payout_result(db_session)
    payout = Payout(
        owner_id=group.owner_id,
        auction_result_id=result.id,
        subscriber_id=membership.subscriber_id,
        membership_id=membership.id,
        gross_amount=200000,
        deductions_amount=12000,
        net_amount=188000,
        payout_method="auction_settlement",
        payout_date=datetime(2026, 5, 10, tzinfo=timezone.utc).date(),
        reference_no=None,
        status="settled",
    )
    db_session.add(payout)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        ensure_auction_payout(db_session, result=result)

    assert exc_info.value.status_code == 409


def test_ensure_auction_payout_rejects_owner_mismatch(app, db_session):
    group, membership, _session, result = _seed_payout_result(db_session)
    payout = Payout(
        owner_id=group.owner_id + 1,
        auction_result_id=result.id,
        subscriber_id=membership.subscriber_id,
        membership_id=membership.id,
        gross_amount=200000,
        deductions_amount=12000,
        net_amount=188000,
        payout_method="auction_settlement",
        payout_date=datetime(2026, 5, 10, tzinfo=timezone.utc).date(),
        reference_no=None,
        status="pending",
    )
    db_session.add(payout)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        ensure_auction_payout(db_session, result=result)

    assert exc_info.value.status_code == 403
