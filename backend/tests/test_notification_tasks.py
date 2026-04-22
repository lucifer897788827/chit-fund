from datetime import timedelta

from sqlalchemy import select

from app.core import database
from app.models.support import Notification
from app.modules.notifications.delivery_service import CHANNEL_DELIVERY_HANDLERS, NotificationDeliveryRetryableError
from app.modules.notifications.service import create_notification
from app.tasks.notification_tasks import (
    queue_cleanup_read_notifications,
    queue_notification_delivery,
    queue_pending_notification_deliveries,
)


def test_queue_pending_notification_deliveries_marks_pending_notifications_sent(app, db_session, monkeypatch):
    notification_one = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )
    notification_two = create_notification(
        db_session,
        user_id=2,
        owner_id=1,
        channel="in_app",
        title="Payout created",
        message="Your payout is ready.",
    )
    db_session.commit()

    delivered_ids: list[int] = []

    def fake_in_app_delivery(notification):
        delivered_ids.append(notification.id)
        return {
            "channel": "in_app",
            "notificationId": notification.id,
            "delivered": True,
        }

    monkeypatch.setitem(CHANNEL_DELIVERY_HANDLERS, "in_app", fake_in_app_delivery)

    results = queue_pending_notification_deliveries.delay(limit=10)

    assert [result["notificationId"] for result in results] == [notification_one.id, notification_two.id]
    assert delivered_ids == [notification_one.id, notification_two.id]

    with database.SessionLocal() as verification_db:
        stored_notifications = verification_db.scalars(
            select(Notification).where(Notification.id.in_([notification_one.id, notification_two.id]))
        ).all()
    assert {notification.status for notification in stored_notifications} == {"sent"}
    assert all(notification.sent_at is not None for notification in stored_notifications)


def test_queue_notification_delivery_marks_failed_notifications_without_sent_at(app, db_session, monkeypatch):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )
    db_session.commit()

    def failing_in_app_delivery(_notification):
        raise RuntimeError("channel offline")

    monkeypatch.setitem(CHANNEL_DELIVERY_HANDLERS, "in_app", failing_in_app_delivery)

    result = queue_notification_delivery.delay(notification.id)

    assert result["notificationId"] == notification.id
    assert result["status"] == "failed"
    assert "channel offline" in result["error"]

    with database.SessionLocal() as verification_db:
        stored = verification_db.scalar(select(Notification).where(Notification.id == notification.id))
    assert stored is not None
    assert stored.status == "failed"
    assert stored.sent_at is None


def test_queue_notification_delivery_retries_transient_delivery_errors(app, db_session, monkeypatch):
    notification = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Auction finalized",
        message="Your auction was finalized successfully.",
    )
    db_session.commit()

    attempts: list[int] = []

    def flaky_in_app_delivery(notification_row):
        attempts.append(notification_row.id)
        if len(attempts) == 1:
            raise NotificationDeliveryRetryableError("temporary outage")
        return {
            "channel": "in_app",
            "notificationId": notification_row.id,
            "delivered": True,
        }

    monkeypatch.setitem(CHANNEL_DELIVERY_HANDLERS, "in_app", flaky_in_app_delivery)

    result = queue_notification_delivery.delay(notification.id)

    assert result["notificationId"] == notification.id
    assert result["status"] == "sent"
    assert attempts == [notification.id, notification.id]

    with database.SessionLocal() as verification_db:
        stored = verification_db.scalar(select(Notification).where(Notification.id == notification.id))
    assert stored is not None
    assert stored.status == "sent"
    assert stored.sent_at is not None


def test_queue_cleanup_read_notifications_deletes_only_stale_read_rows(app, db_session):
    stale_read = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Stale read",
        message="This read notification should be cleaned up.",
    )
    stale_read.created_at = stale_read.created_at - timedelta(days=60)
    stale_read.read_at = stale_read.created_at + timedelta(minutes=5)

    recent_read = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Recent read",
        message="This read notification should stay.",
    )
    recent_read.created_at = recent_read.created_at - timedelta(days=2)
    recent_read.read_at = recent_read.created_at + timedelta(minutes=5)

    unread = create_notification(
        db_session,
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Unread",
        message="Unread notifications should never be deleted.",
    )
    db_session.commit()

    result = queue_cleanup_read_notifications.delay(older_than_days=30, limit=100)

    assert result == {
        "deletedCount": 1,
        "cutoffDays": 30,
    }

    with database.SessionLocal() as verification_db:
        remaining_titles = verification_db.scalars(
            select(Notification.title).order_by(Notification.id.asc())
        ).all()

    assert remaining_titles == ["Recent read", "Unread"]
