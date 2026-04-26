from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.auction import AuctionBid, AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.support import Notification
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.service import finalize_auction
from app.modules.notifications.service import create_notification
from app.modules.notifications.email_service import NotificationEmailDeliveryService


def _seed_finalizable_auction(db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="NOTIF-AUC-001",
        title="Notification Group",
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

    owner_user = db_session.get(User, 1)
    owner_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id))

    winner_user = User(
        email="winner@example.com",
        phone="7777777777",
        password_hash="not-used",
        role="subscriber",
        is_active=True,
    )
    db_session.add(winner_user)
    db_session.flush()

    winner_subscriber = Subscriber(
        user_id=winner_user.id,
        owner_id=1,
        full_name="Winner One",
        phone=winner_user.phone,
        email=winner_user.email,
        status="active",
    )
    db_session.add(winner_subscriber)
    db_session.flush()

    owner_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=owner_subscriber.id,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    winner_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=winner_subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([owner_membership, winner_membership])
    db_session.flush()

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2026, 7, 10, 10, 3, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="closed",
        opened_by_user_id=1,
        closed_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    winning_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=winner_membership.id,
        bidder_user_id=winner_user.id,
        idempotency_key="winner-bid",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 0, 10, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(winning_bid)
    return session, winning_bid, owner_user, winner_user


def test_create_notification_persists_pending_in_app_notification(app, db_session):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )

    stored = db_session.scalar(select(Notification).where(Notification.id == notification.id))

    assert stored is not None
    assert stored.user_id == 1
    assert stored.owner_id == 1
    assert stored.channel == "in_app"
    assert stored.title == "Auction finalized"
    assert stored.message == "Your auction was finalized successfully."
    assert stored.status == "pending"
    assert stored.sent_at is None
    assert stored.read_at is None


def test_create_notification_normalizes_read_status_timestamps(app, db_session):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Read notification",
        message="This notification should already be marked read.",
        status="read",
    )

    stored = db_session.scalar(select(Notification).where(Notification.id == notification.id))

    assert stored is not None
    assert stored.status == "read"
    assert stored.read_at is not None
    assert stored.sent_at is None


class FakeSMTPClient:
    def __init__(self):
        self.started_tls = False
        self.login_calls = []
        self.sent_messages = []
        self.quit_called = False

    def starttls(self, context=None):
        self.started_tls = True
        self.starttls_context = context

    def login(self, username, password):
        self.login_calls.append((username, password))

    def send_message(self, message):
        self.sent_messages.append(message)

    def quit(self):
        self.quit_called = True


def test_email_delivery_service_skips_when_smtp_is_not_configured(app, db_session):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="email",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )
    service = NotificationEmailDeliveryService(
        app_name="Chit Fund Platform",
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_from_address=None,
        smtp_use_tls=True,
        smtp_use_ssl=False,
        smtp_timeout_seconds=10.0,
    )

    result = service.deliver(db_session, notification)

    assert result.delivered is False
    assert result.skipped is True
    assert result.reason == "smtp is not configured"
    assert notification.status == "pending"
    assert notification.sent_at is None


def test_email_delivery_service_sends_and_marks_notification_sent(app, db_session):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="email",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )
    smtp_client = FakeSMTPClient()
    service = NotificationEmailDeliveryService(
        app_name="Chit Fund Platform",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer@example.com",
        smtp_password="smtp-secret",
        smtp_from_address="notifications@example.com",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        smtp_timeout_seconds=10.0,
        smtp_factory=lambda *args, **kwargs: smtp_client,
        smtp_ssl_factory=lambda *args, **kwargs: smtp_client,
    )

    result = service.deliver(db_session, notification)

    assert result.delivered is True
    assert result.skipped is False
    assert smtp_client.started_tls is True
    assert smtp_client.login_calls == [("mailer@example.com", "smtp-secret")]
    assert smtp_client.quit_called is True
    assert len(smtp_client.sent_messages) == 1
    message = smtp_client.sent_messages[0]
    assert message["Subject"] == "Auction finalized"
    assert message["From"] == "Chit Fund Platform <notifications@example.com>"
    assert message["To"] == "owner@example.com"
    assert message.get_content().strip() == "Your auction was finalized successfully."
    assert notification.status == "sent"
    assert notification.sent_at is not None


def test_finalize_auction_creates_notifications_for_owner_and_winner(app, db_session, monkeypatch):
    session, _winning_bid, owner_user, winner_user = _seed_finalizable_auction(db_session)
    owner_subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == owner_user.id))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id))
    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=owner_subscriber)
    monkeypatch.setattr("app.modules.auctions.service.ensure_auction_payout", lambda *args, **kwargs: None)

    result = finalize_auction(db_session, session.id, current_user=current_user)

    notifications = db_session.scalars(
        select(Notification).where(Notification.title == f"Auction finalized for cycle {result['cycleNo']}")
    ).all()

    assert len(notifications) == 4
    assert {notification.user_id for notification in notifications} == {owner_user.id, winner_user.id}
    assert {notification.channel for notification in notifications} == {"in_app", "email"}
    assert {notification.status for notification in notifications} == {"pending"}
