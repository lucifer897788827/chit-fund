from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.core.security import CurrentUser
from app.core.config import settings
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payout
from app.models.support import Notification
from app.models.user import Owner, Subscriber, User
from app.modules.auth.service import confirm_password_reset, request_password_reset
from app.modules.notifications.service import dispatch_staged_notifications
from app.modules.payments.payout_service import ensure_auction_payout, settle_owner_payout
from app.modules.payments.service import record_payment


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _seed_group_membership(db_session, *, group_code: str, title: str):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.id == 2))
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
        subscriber_id=subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    return owner, subscriber, group, membership


def _seed_finalizable_auction(db_session):
    owner, subscriber, group, membership = _seed_group_membership(
        db_session,
        group_code="HOOK-AUC-001",
        title="Hook Auction Group",
    )

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="hook-winner-bid",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(winning_bid)
    return owner, subscriber, group, membership, session, winning_bid


def _seed_auction_result(db_session):
    owner, subscriber, group, membership = _seed_group_membership(
        db_session,
        group_code="HOOK-PAYOUT-001",
        title="Hook Payout Group",
    )

    session = AuctionSession(
        group_id=group.id,
        cycle_no=3,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=owner.user_id,
        closed_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=subscriber.user_id,
        idempotency_key="hook-payout-bid",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.flush()

    result = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=session.cycle_no,
        winner_membership_id=membership.id,
        winning_bid_id=winning_bid.id,
        winning_bid_amount=12000,
        dividend_pool_amount=0,
        dividend_per_member_amount=0,
        owner_commission_amount=0,
        winner_payout_amount=188000,
        finalized_by_user_id=owner.user_id,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
    )
    db_session.add(result)
    db_session.commit()
    return owner, subscriber, group, membership, session, result


def test_record_payment_creates_owner_and_subscriber_notifications(app, db_session):
    owner, subscriber, group, membership = _seed_group_membership(
        db_session,
        group_code="HOOK-PAY-001",
        title="Hook Payment Group",
    )
    installment = Installment(
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_date=date(2026, 7, 15),
        due_amount=10000,
        penalty_amount=0,
        paid_amount=0,
        balance_amount=10000,
        status="pending",
    )
    db_session.add(installment)
    db_session.commit()

    payload = SimpleNamespace(
        ownerId=owner.id,
        subscriberId=subscriber.id,
        membershipId=membership.id,
        installmentId=installment.id,
        paymentType="installment",
        paymentMethod="cash",
        amount=10000,
        paymentDate=date(2026, 7, 15),
        referenceNo="PAY-HOOK-001",
    )

    result = record_payment(db_session, payload, _owner_current_user(db_session))

    notifications = db_session.scalars(
        select(Notification).where(Notification.title == f"Payment recorded for {subscriber.full_name}")
    ).all()

    assert result["id"] is not None
    assert len(notifications) == 4
    assert {notification.user_id for notification in notifications} == {owner.user_id, subscriber.user_id}
    assert {notification.channel for notification in notifications} == {"in_app", "email"}


def test_ensure_auction_payout_creates_notifications_for_owner_and_winner(app, db_session):
    owner, subscriber, group, membership, _session, result = _seed_auction_result(db_session)

    payout, _ledger_entry = ensure_auction_payout(db_session, result=result)

    notifications = db_session.scalars(
        select(Notification).where(Notification.title == f"Payout created for {subscriber.full_name}")
    ).all()

    assert payout.owner_id == owner.id
    assert len(notifications) == 4
    assert {notification.user_id for notification in notifications} == {owner.user_id, subscriber.user_id}
    assert {notification.channel for notification in notifications} == {"in_app", "email"}


def test_settle_owner_payout_creates_settlement_notifications(app, db_session):
    owner, subscriber, _group, _membership, _session, result = _seed_auction_result(db_session)
    payout = db_session.scalar(select(Payout).where(Payout.auction_result_id == result.id))
    assert payout is None
    payout, _ledger_entry = ensure_auction_payout(db_session, result=result)
    db_session.commit()
    dispatch_staged_notifications(db_session)

    serialized = settle_owner_payout(
        db_session,
        payout.id,
        _owner_current_user(db_session),
        reference_no="SETTLE-HOOK-001",
    )

    notifications = db_session.scalars(
        select(Notification).where(Notification.title == f"Payout settled for {subscriber.full_name}")
    ).all()

    assert serialized["status"] == "settled"
    assert payout.owner_id == owner.id
    assert len(notifications) == 4
    assert {notification.user_id for notification in notifications} == {owner.user_id, subscriber.user_id}
    assert {notification.channel for notification in notifications} == {"in_app", "email"}


def test_password_reset_request_and_confirmation_create_notifications(app, db_session):
    original_app_env = settings.app_env
    settings.app_env = "development"
    try:
        request_result = request_password_reset(db_session, "9999999999")
        assert request_result["reset_token"] is not None

        request_notifications = db_session.scalars(
            select(Notification).where(Notification.title == "Password reset requested")
        ).all()
        assert len(request_notifications) == 2
        assert {notification.user_id for notification in request_notifications} == {1}
        assert {notification.channel for notification in request_notifications} == {"in_app", "email"}

        confirm_result = confirm_password_reset(db_session, request_result["reset_token"], "reset-secret-123")
        assert confirm_result["message"] == "Password has been reset"

        all_notifications = db_session.scalars(
            select(Notification).where(Notification.user_id == 1).order_by(Notification.id)
        ).all()

        assert len(all_notifications) == 4
        assert [notification.title for notification in all_notifications[:2]] == [
            "Password reset requested",
            "Password reset requested",
        ]
        assert [notification.title for notification in all_notifications[2:]] == [
            "Password reset completed",
            "Password reset completed",
        ]
    finally:
        settings.app_env = original_app_env


def test_dispatch_staged_notifications_skips_broker_publish_when_not_eager(app, db_session, monkeypatch):
    owner, subscriber, _group, _membership = _seed_group_membership(
        db_session,
        group_code="HOOK-DISPATCH-001",
        title="Hook Dispatch Group",
    )
    notification = Notification(
        user_id=owner.user_id,
        owner_id=owner.id,
        channel="email",
        title=f"Dispatch test for {subscriber.full_name}",
        message="Dispatch test payload",
        status="pending",
        created_at=datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(notification)
    db_session.flush()
    db_session.info["pending_notification_dispatch"] = [notification]

    class _ShouldNotPublish:
        def delay(self, _notification_id):
            raise AssertionError("Broker publish should be skipped when celery is not eager")

    from app.core.celery_app import celery_app

    previous_task_always_eager = celery_app.conf.task_always_eager
    monkeypatch.setattr("app.tasks.notification_tasks.queue_notification_delivery", _ShouldNotPublish())
    celery_app.conf.task_always_eager = False
    try:
        dispatch_staged_notifications(db_session)
    finally:
        celery_app.conf.task_always_eager = previous_task_always_eager
