from datetime import datetime, timezone

from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Owner, Subscriber
from app.modules.auctions.service import (
    finalize_expired_open_auction_sessions,
    get_auction_session_deadline,
    list_expired_open_auction_sessions,
)
from app.tasks.auction_tasks import queue_expired_auction_auto_close


def _seed_group_with_member(db_session, *, group_code: str, title: str, start_at: datetime) -> tuple[ChitGroup, GroupMembership]:
    owner = db_session.scalar(select(Owner).where(Owner.user_id == 1))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == 2))
    assert owner is not None
    assert subscriber is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code=group_code,
        title=title,
        chit_value=200000,
        installment_amount=10000,
        member_count=20,
        cycle_count=20,
        cycle_frequency="monthly",
        start_date=start_at.date(),
        first_auction_date=start_at.date(),
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
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    return group, membership


def _seed_session(
    db_session,
    *,
    group: ChitGroup,
    membership: GroupMembership,
    session_code: str,
    status: str,
    scheduled_start_at: datetime,
    actual_start_at: datetime | None,
    bidding_window_seconds: int,
    auction_mode: str = "LIVE",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=scheduled_start_at,
        actual_start_at=actual_start_at,
        actual_end_at=None,
        start_time=start_time,
        end_time=end_time,
        auction_mode=auction_mode,
        bidding_window_seconds=bidding_window_seconds,
        status=status,
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=2,
        idempotency_key=session_code,
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=scheduled_start_at,
        is_valid=True,
    )
    db_session.add(bid)
    db_session.flush()
    return session, bid


def test_get_auction_session_deadline_prefers_actual_start_at_when_present(app, db_session):
    group, membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-001",
        title="Auto Close Deadline Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    session, _bid = _seed_session(
        db_session,
        group=group,
        membership=membership,
        session_code="deadline-actual",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        bidding_window_seconds=180,
    )

    assert get_auction_session_deadline(session) == datetime(2026, 7, 10, 10, 8, tzinfo=timezone.utc)


def test_get_auction_session_deadline_uses_explicit_blind_end_time(app, db_session):
    group, membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-001B",
        title="Blind Auto Close Deadline Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    session, _bid = _seed_session(
        db_session,
        group=group,
        membership=membership,
        session_code="deadline-blind-end",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        auction_mode="BLIND",
        start_time=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 7, 10, 10, 6, tzinfo=timezone.utc),
        bidding_window_seconds=180,
    )

    assert get_auction_session_deadline(session) == datetime(2026, 7, 10, 10, 6, tzinfo=timezone.utc)


def test_list_expired_open_auction_sessions_uses_scheduled_start_at_when_actual_is_missing(app, db_session):
    expired_group, expired_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-002",
        title="Expired Scheduled Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    expired_session, _ = _seed_session(
        db_session,
        group=expired_group,
        membership=expired_membership,
        session_code="expired-scheduled",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=60,
    )

    active_group, active_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-003",
        title="Active Scheduled Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    active_session, _ = _seed_session(
        db_session,
        group=active_group,
        membership=active_membership,
        session_code="active-scheduled",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 10, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=600,
    )

    expired_sessions = list_expired_open_auction_sessions(
        db_session,
        now=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
    )

    assert [session.id for session in expired_sessions] == [expired_session.id]
    assert active_session.id not in {session.id for session in expired_sessions}


def test_list_expired_open_auction_sessions_applies_limit_after_expiry_filter(app, db_session):
    upcoming_group, upcoming_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-003A",
        title="Upcoming Before Expired Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    _seed_session(
        db_session,
        group=upcoming_group,
        membership=upcoming_membership,
        session_code="upcoming-first",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 10, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=600,
    )

    expired_group, expired_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-003B",
        title="Expired After Upcoming Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    expired_session, _ = _seed_session(
        db_session,
        group=expired_group,
        membership=expired_membership,
        session_code="expired-after-upcoming",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=60,
    )

    expired_sessions = list_expired_open_auction_sessions(
        db_session,
        now=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
        limit=1,
    )

    assert [session.id for session in expired_sessions] == [expired_session.id]


def test_finalize_expired_open_auction_sessions_finalizes_only_expired_sessions(app, db_session):
    expired_group, expired_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-004",
        title="Expired Finalize Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    expired_session, expired_bid = _seed_session(
        db_session,
        group=expired_group,
        membership=expired_membership,
        session_code="expired-finalize",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=120,
    )

    active_group, active_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-005",
        title="Active Finalize Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    active_session, _ = _seed_session(
        db_session,
        group=active_group,
        membership=active_membership,
        session_code="active-finalize",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 12, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=600,
    )

    finalized_sessions = finalize_expired_open_auction_sessions(
        db_session,
        now=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
    )

    db_session.refresh(expired_session)
    db_session.refresh(active_session)
    expired_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == expired_session.id))
    active_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == active_session.id))

    assert [row["sessionId"] for row in finalized_sessions] == [expired_session.id]
    assert expired_session.status == "finalized"
    assert expired_session.closed_by_user_id == 1
    assert expired_session.winning_bid_id == expired_bid.id
    assert expired_result is not None
    assert expired_result.winning_bid_id == expired_bid.id
    assert active_session.status == "open"
    assert active_result is None


def test_finalize_expired_open_auction_sessions_skips_expired_sessions_without_valid_bids(app, db_session):
    blocked_group, blocked_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-006",
        title="Blocked Expired Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    blocked_session, blocked_bid = _seed_session(
        db_session,
        group=blocked_group,
        membership=blocked_membership,
        session_code="expired-invalid-only",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=60,
    )
    blocked_bid.is_valid = False
    blocked_bid.invalid_reason = "not-eligible"

    valid_group, valid_membership = _seed_group_with_member(
        db_session,
        group_code="AUTO-CLOSE-007",
        title="Valid Expired Group",
        start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )
    valid_session, valid_bid = _seed_session(
        db_session,
        group=valid_group,
        membership=valid_membership,
        session_code="expired-valid-later",
        status="open",
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=None,
        bidding_window_seconds=60,
    )
    db_session.commit()

    finalized_sessions = finalize_expired_open_auction_sessions(
        db_session,
        now=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
    )

    db_session.refresh(blocked_session)
    db_session.refresh(valid_session)
    blocked_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == blocked_session.id))
    valid_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == valid_session.id))

    assert [row["sessionId"] for row in finalized_sessions] == [valid_session.id]
    assert blocked_session.status == "open"
    assert blocked_result is None
    assert valid_session.status == "finalized"
    assert valid_result is not None
    assert valid_result.winning_bid_id == valid_bid.id


def test_queue_expired_auction_auto_close_exposes_a_queueable_task(monkeypatch):
    from types import SimpleNamespace

    class FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.tasks.auction_tasks.database.SessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "app.tasks.auction_tasks.start_job_run",
        lambda *args, **kwargs: SimpleNamespace(id=123),
    )
    monkeypatch.setattr("app.tasks.auction_tasks.complete_job_run", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.tasks.auction_tasks.fail_job_run", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.tasks.auction_tasks.log_job_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.tasks.auction_tasks._update_job_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.tasks.auction_tasks.finalize_expired_open_auction_sessions",
        lambda db, limit=200: [{"sessionId": 99, "status": "finalized", "limit": limit}],
    )

    queued = queue_expired_auction_auto_close.delay(limit=25)

    assert queued == [{"sessionId": 99, "status": "finalized", "limit": 25}]
