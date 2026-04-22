from __future__ import annotations

from collections.abc import Callable
import smtplib
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, object_session

from app.core.time import utcnow
from app.models.support import Notification
from app.modules.notifications.email_service import NotificationEmailDeliveryService
from app.modules.notifications.sms import send_sms


NotificationDeliveryHandler = Callable[[Notification], dict[str, Any]]
MAX_PENDING_NOTIFICATION_BATCH = 500


def _normalize_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_PENDING_NOTIFICATION_BATCH))


class NotificationDeliveryError(RuntimeError):
    pass


class NotificationDeliveryRetryableError(NotificationDeliveryError):
    pass


def deliver_in_app_notification(notification: Notification) -> dict[str, Any]:
    return {
        "channel": "in_app",
        "notificationId": notification.id,
        "delivered": True,
    }


def deliver_email_notification(notification: Notification) -> dict[str, Any]:
    service = NotificationEmailDeliveryService.from_settings()
    db = object_session(notification)
    if db is None:
        raise ValueError("Notification is not attached to a database session")
    with db.no_autoflush:
        try:
            result = service.deliver(db, notification)
        except (ConnectionError, TimeoutError, OSError, smtplib.SMTPException) as exc:
            raise NotificationDeliveryRetryableError(str(exc)) from exc
    return {
        "channel": "email",
        "notificationId": notification.id,
        "delivered": result.delivered,
        "skipped": result.skipped,
        "reason": result.reason,
    }


def deliver_sms_notification(notification: Notification) -> dict[str, Any]:
    try:
        result = send_sms(
            recipient=f"user:{notification.user_id}",
            message=notification.message,
        )
    except (ConnectionError, TimeoutError, OSError) as exc:
        raise NotificationDeliveryRetryableError(str(exc)) from exc
    return {
        "channel": "sms",
        "notificationId": notification.id,
        "delivered": result.delivered,
        "reason": result.skipped_reason,
        "provider": result.provider,
    }


CHANNEL_DELIVERY_HANDLERS: dict[str, NotificationDeliveryHandler] = {
    "in_app": deliver_in_app_notification,
    "email": deliver_email_notification,
    "sms": deliver_sms_notification,
}


def _claim_pending_notification(db: Session, notification_id: int) -> Notification | None:
    claimed = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == "pending",
        )
        .values(status="processing")
    )
    if claimed.rowcount != 1:
        db.rollback()
        return db.scalar(select(Notification).where(Notification.id == notification_id))

    db.commit()
    return db.scalar(select(Notification).where(Notification.id == notification_id))


def _mark_notification_failed(db: Session, notification_id: int) -> Notification | None:
    db.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(status="failed")
    )
    db.commit()
    return db.scalar(select(Notification).where(Notification.id == notification_id))


def _mark_notification_sent(db: Session, notification_id: int) -> Notification | None:
    db.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(status="sent", sent_at=utcnow())
    )
    db.commit()
    return db.scalar(select(Notification).where(Notification.id == notification_id))


def _mark_notification_skipped(db: Session, notification_id: int) -> Notification | None:
    db.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(status="skipped")
    )
    db.commit()
    return db.scalar(select(Notification).where(Notification.id == notification_id))


def deliver_notification_by_channel(notification: Notification) -> dict[str, Any]:
    handler = CHANNEL_DELIVERY_HANDLERS.get(notification.channel)
    if handler is None:
        raise NotificationDeliveryError(f"Unsupported notification channel: {notification.channel}")
    return handler(notification)


def deliver_notification(db: Session, notification_id: int) -> dict[str, Any]:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id))
    if notification is None:
        return {
            "notificationId": notification_id,
            "status": "missing",
        }

    if notification.status not in {"pending", "processing"}:
        return {
            "notificationId": notification.id,
            "status": notification.status,
            "channel": notification.channel,
            "sentAt": notification.sent_at,
        }

    claimed = notification
    if notification.status == "pending":
        claimed = _claim_pending_notification(db, notification_id)
        if claimed is None:
            return {
                "notificationId": notification_id,
                "status": "missing",
            }
        if claimed.status != "processing":
            return {
                "notificationId": claimed.id,
                "status": claimed.status,
                "channel": claimed.channel,
                "sentAt": claimed.sent_at,
            }

    try:
        delivery_result = deliver_notification_by_channel(claimed)
    except NotificationDeliveryRetryableError:
        raise
    except Exception as exc:
        failed = _mark_notification_failed(db, notification_id)
        return {
            "notificationId": notification_id,
            "status": "failed",
            "channel": failed.channel if failed is not None else claimed.channel,
            "error": str(exc),
            "sentAt": failed.sent_at if failed is not None else None,
        }

    if delivery_result.get("skipped"):
        skipped = _mark_notification_skipped(db, notification_id)
        return {
            "notificationId": notification_id,
            "status": skipped.status if skipped is not None else "skipped",
            "channel": skipped.channel if skipped is not None else claimed.channel,
            "sentAt": skipped.sent_at if skipped is not None else None,
            "delivery": delivery_result,
        }

    sent = _mark_notification_sent(db, notification_id)
    return {
        "notificationId": notification_id,
        "status": sent.status if sent is not None else "sent",
        "channel": sent.channel if sent is not None else claimed.channel,
        "sentAt": sent.sent_at if sent is not None else utcnow(),
        "delivery": delivery_result,
    }


def mark_notification_failed(db: Session, notification_id: int) -> Notification | None:
    return _mark_notification_failed(db, notification_id)


def deliver_pending_notifications(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    normalized_limit = _normalize_limit(limit)
    pending_notification_ids = db.scalars(
        select(Notification.id)
        .where(Notification.status == "pending")
        .order_by(Notification.id.asc())
        .limit(normalized_limit)
    ).all()

    results: list[dict[str, Any]] = []
    for notification_id in pending_notification_ids:
        results.append(deliver_notification(db, notification_id))
    return results
