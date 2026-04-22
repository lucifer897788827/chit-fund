from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import LedgerEntry, Payout
from app.models.user import Owner, Subscriber, User
from app.modules.payments.payout_service import _upsert_payout_ledger_entry, settle_owner_payout


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _seed_auction_result(db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="PAYOUT-001",
        title="Payout Group",
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
        subscriber_id=2,
        member_no=4,
        membership_status="active",
        prized_status="prized",
        can_bid=False,
    )
    db_session.add(membership)
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=3,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="payout-ledger-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.flush()

    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=3,
        winner_membership_id=membership.id,
        winning_bid_id=winning_bid.id,
        winning_bid_amount=12000,
        dividend_pool_amount=5000,
        dividend_per_member_amount=250,
        owner_commission_amount=1000,
        winner_payout_amount=188000,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.flush()

    payout = Payout(
        owner_id=group.owner_id,
        auction_result_id=result.id,
        subscriber_id=membership.subscriber_id,
        membership_id=membership.id,
        gross_amount=200000,
        deductions_amount=12000,
        net_amount=188000,
        payout_method="bank_transfer",
        payout_date=date(2026, 7, 11),
        status="pending",
    )
    db_session.add(payout)
    db_session.flush()

    stale_entry = LedgerEntry(
        owner_id=group.owner_id,
        entry_date=date(2026, 7, 9),
        entry_type="payout",
        source_table="payouts",
        source_id=payout.id,
        subscriber_id=membership.subscriber_id,
        group_id=group.id,
        debit_amount=0,
        credit_amount=1000,
        description="Stale payout ledger row",
    )
    db_session.add(stale_entry)
    db_session.commit()
    return result, payout, stale_entry


def test_settle_owner_payout_updates_ledger_entry_in_place(app, db_session):
    result, payout, stale_entry = _seed_auction_result(db_session)
    current_user = _owner_current_user(db_session)

    serialized = settle_owner_payout(
        db_session,
        payout.id,
        current_user,
        reference_no="SETTLE-001",
    )

    assert serialized["id"] == payout.id
    assert serialized["status"] == "settled"
    assert serialized["referenceNo"] == "SETTLE-001"

    persisted = db_session.scalar(select(LedgerEntry).where(LedgerEntry.id == stale_entry.id))
    assert persisted is not None
    assert persisted.source_table == "payouts"
    assert persisted.source_id == payout.id
    assert persisted.group_id == result.group_id
    assert float(persisted.credit_amount) == 188000.0
    assert float(persisted.debit_amount) == 0.0
    assert persisted.entry_date == date(2026, 7, 11)

    updated_payout = db_session.get(Payout, payout.id)
    assert updated_payout is not None
    assert updated_payout.status == "settled"
    assert updated_payout.reference_no == "SETTLE-001"


def test_upsert_payout_ledger_entry_uses_result_finalized_date_when_payout_date_missing(app, db_session):
    result, payout, stale_entry = _seed_auction_result(db_session)
    payout.payout_date = None
    db_session.commit()

    updated_entry = _upsert_payout_ledger_entry(db_session, payout, result)

    assert updated_entry.id == stale_entry.id
    assert updated_entry.entry_date == result.finalized_at.date()
