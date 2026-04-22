from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser
from app.core.time import utcnow
from app.models.auction import AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payout
from app.models.support import Notification
from app.models.user import Owner, Subscriber, User


_NOTIFICATION_DISPATCH_KEY = "pending_notification_dispatch"
MAX_NOTIFICATION_CLEANUP_LIMIT = 500


def _normalize_limit(limit: int, *, maximum: int) -> int:
    return max(1, min(int(limit), maximum))


def create_notification(
    db: Session,
    *,
    user_id: int,
    owner_id: int | None = None,
    channel: str = "in_app",
    title: str,
    message: str,
    status: str = "pending",
) -> Notification:
    normalized_status = (status or "pending").strip().lower()
    if not normalized_status:
        normalized_status = "pending"

    now = utcnow()
    notification = Notification(
        user_id=user_id,
        owner_id=owner_id,
        channel=channel,
        title=title[:255],
        message=message[:1000],
        status=normalized_status,
        created_at=now,
        sent_at=now if normalized_status == "sent" else None,
        read_at=now if normalized_status == "read" else None,
    )
    db.add(notification)
    db.flush()
    db.refresh(notification)
    return notification


def stage_notification_dispatch(db: Session, notifications: list[Notification]) -> None:
    if not notifications:
        return
    staged = db.info.setdefault(_NOTIFICATION_DISPATCH_KEY, [])
    staged.extend(notifications)


def dispatch_staged_notifications(db: Session) -> None:
    staged = db.info.pop(_NOTIFICATION_DISPATCH_KEY, [])
    if not staged:
        return

    try:
        from app.tasks.notification_tasks import queue_notification_delivery
    except ModuleNotFoundError:
        return

    for notification in staged:
        if notification.channel == "in_app":
            continue
        try:
            queue_notification_delivery.delay(notification.id)
        except Exception:
            continue


def _current_owner_id(current_user: CurrentUser) -> int | None:
    if current_user.owner is not None:
        return current_user.owner.id
    if current_user.subscriber is not None:
        return current_user.subscriber.owner_id
    return None


def _notification_is_accessible(notification: Notification, current_user: CurrentUser) -> bool:
    if notification.user_id != current_user.user.id:
        return False

    owner_id = _current_owner_id(current_user)
    if notification.owner_id is None or owner_id is None:
        return notification.owner_id is None

    return notification.owner_id == owner_id


def _notification_access_filter(current_user: CurrentUser):
    owner_id = _current_owner_id(current_user)
    if owner_id is None:
        return Notification.owner_id.is_(None)

    return (Notification.owner_id.is_(None)) | (Notification.owner_id == owner_id)


def list_notifications(
    db: Session,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    statement = (
        select(Notification)
        .where(
            Notification.user_id == current_user.user.id,
            _notification_access_filter(current_user),
        )
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        notifications = db.scalars(statement).all()
        return [_serialize_notification(notification) for notification in notifications]

    total_count = count_statement(db, statement)
    notifications = db.scalars(apply_pagination(statement, pagination)).all()
    return build_paginated_response([_serialize_notification(notification) for notification in notifications], pagination, total_count)


def mark_notification_as_read(db: Session, notification_id: int, current_user: CurrentUser) -> dict:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id))
    if notification is None:
        raise ValueError("Notification not found")

    if notification.user_id != current_user.user.id:
        raise ValueError("Notification not found")

    if not _notification_is_accessible(notification, current_user):
        raise PermissionError("Notification does not belong to the current owner or subscriber")

    notification.status = "read"
    if notification.read_at is None:
        notification.read_at = utcnow()
        db.commit()
        db.refresh(notification)

    return _serialize_notification(notification)


def prune_read_notifications(
    db: Session,
    *,
    older_than_days: int = 30,
    limit: int = 500,
) -> dict[str, int]:
    normalized_limit = _normalize_limit(limit, maximum=MAX_NOTIFICATION_CLEANUP_LIMIT)
    cutoff_at = utcnow() - timedelta(days=older_than_days)
    stale_notification_ids = db.scalars(
        select(Notification.id)
        .where(
            Notification.read_at.is_not(None),
            Notification.read_at < cutoff_at,
        )
        .order_by(Notification.read_at.asc(), Notification.id.asc())
        .limit(normalized_limit)
    ).all()

    if not stale_notification_ids:
        return {
            "deletedCount": 0,
            "cutoffDays": older_than_days,
        }

    db.execute(delete(Notification).where(Notification.id.in_(stale_notification_ids)))
    db.commit()
    return {
        "deletedCount": len(stale_notification_ids),
        "cutoffDays": older_than_days,
    }


def _serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "userId": notification.user_id,
        "ownerId": notification.owner_id,
        "channel": notification.channel,
        "title": notification.title,
        "message": notification.message,
        "status": notification.status,
        "createdAt": notification.created_at,
        "sentAt": notification.sent_at,
        "readAt": notification.read_at,
    }


def _has_email_address(db: Session, user_id: int) -> bool:
    email = db.scalar(select(User.email).where(User.id == user_id))
    return bool(email)


def _append_channel_notifications(
    notifications: list[Notification],
    *,
    db: Session,
    user_id: int,
    owner_id: int | None,
    title: str,
    message: str,
) -> None:
    in_app_notification = _create_notification_if_missing(
        db,
        user_id=user_id,
        owner_id=owner_id,
        channel="in_app",
        title=title,
        message=message,
    )
    if in_app_notification is not None:
        notifications.append(in_app_notification)

    if _has_email_address(db, user_id):
        email_notification = _create_notification_if_missing(
            db,
            user_id=user_id,
            owner_id=owner_id,
            channel="email",
            title=title,
            message=message,
        )
        if email_notification is not None:
            notifications.append(email_notification)


def _notification_exists(
    db: Session,
    *,
    user_id: int,
    owner_id: int | None,
    channel: str,
    title: str,
    message: str,
) -> bool:
    return (
        db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.owner_id.is_(owner_id) if owner_id is None else Notification.owner_id == owner_id,
                Notification.channel == channel,
                Notification.title == title[:255],
                Notification.message == message[:1000],
            )
        )
        is not None
    )


def _create_notification_if_missing(
    db: Session,
    *,
    user_id: int,
    owner_id: int | None,
    channel: str,
    title: str,
    message: str,
) -> Notification | None:
    if _notification_exists(
        db,
        user_id=user_id,
        owner_id=owner_id,
        channel=channel,
        title=title,
        message=message,
    ):
        return None
    return create_notification(
        db,
        user_id=user_id,
        owner_id=owner_id,
        channel=channel,
        title=title,
        message=message,
    )


def notify_auction_finalized(db: Session, *, session: AuctionSession, result: AuctionResult) -> list[Notification]:
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == session.group_id))
    if group is None:
        return []

    owner = db.scalar(select(Owner).where(Owner.id == group.owner_id))
    winner_membership = db.scalar(
        select(GroupMembership).where(GroupMembership.id == result.winner_membership_id)
    )
    if owner is None or winner_membership is None:
        return []

    winner_subscriber = db.scalar(
        select(Subscriber).where(Subscriber.id == winner_membership.subscriber_id)
    )
    if winner_subscriber is None:
        return []

    title = f"Auction finalized for cycle {session.cycle_no}"
    message = (
        f"{group.title} was finalized. Winner membership {winner_membership.member_no} "
        f"won with bid {money_int(result.winning_bid_amount)}."
    )
    notifications: list[Notification] = []

    _append_channel_notifications(
        notifications,
        db=db,
        user_id=owner.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=winner_subscriber.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )

    stage_notification_dispatch(db, notifications)
    return notifications


def notify_payment_recorded(db: Session, *, payment) -> list[Notification]:
    owner = db.scalar(select(Owner).where(Owner.id == payment.owner_id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == payment.subscriber_id))
    membership = (
        db.scalar(select(GroupMembership).where(GroupMembership.id == payment.membership_id))
        if payment.membership_id is not None
        else None
    )
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == membership.group_id)) if membership else None
    if owner is None or subscriber is None:
        return []

    group_suffix = f" in {group.title}" if group is not None else ""
    title = f"Payment recorded for {subscriber.full_name}"
    message = (
        f"A {payment.payment_type} payment of {money_int(payment.amount)} was recorded"
        f"{group_suffix}."
    )
    notifications: list[Notification] = []

    _append_channel_notifications(
        notifications,
        db=db,
        user_id=owner.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=subscriber.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )

    stage_notification_dispatch(db, notifications)
    return notifications


def notify_payout_created(db: Session, *, payout: Payout) -> list[Notification]:
    owner = db.scalar(select(Owner).where(Owner.id == payout.owner_id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == payout.subscriber_id))
    if owner is None or subscriber is None:
        return []

    title = f"Payout created for {subscriber.full_name}"
    message = (
        f"A payout of {money_int(payout.net_amount)} was created for {subscriber.full_name} "
        f"from auction result {payout.auction_result_id}."
    )
    notifications: list[Notification] = []

    _append_channel_notifications(
        notifications,
        db=db,
        user_id=owner.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=subscriber.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )

    stage_notification_dispatch(db, notifications)
    return notifications


def notify_payout_settled(db: Session, *, payout: Payout) -> list[Notification]:
    owner = db.scalar(select(Owner).where(Owner.id == payout.owner_id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == payout.subscriber_id))
    if owner is None or subscriber is None:
        return []

    title = f"Payout settled for {subscriber.full_name}"
    message = (
        f"The payout of {money_int(payout.net_amount)} for {subscriber.full_name} "
        f"has been settled."
    )
    notifications: list[Notification] = []

    _append_channel_notifications(
        notifications,
        db=db,
        user_id=owner.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=subscriber.user_id,
        owner_id=owner.id,
        title=title,
        message=message,
    )

    stage_notification_dispatch(db, notifications)
    return notifications


def _payment_reminder_kind(installment: Installment, as_of: date) -> str | None:
    if installment.status == "paid" or money_int(installment.balance_amount) <= 0:
        return None
    if installment.due_date > as_of:
        return None
    return "overdue" if installment.due_date < as_of else "due"


def _payment_reminder_title(group: ChitGroup, installment: Installment, reminder_kind: str) -> str:
    return f"{reminder_kind.title()} payment reminder for {group.title} cycle {installment.cycle_no}"


def _payment_reminder_message(
    group: ChitGroup,
    subscriber: Subscriber,
    installment: Installment,
    reminder_kind: str,
) -> str:
    if reminder_kind == "overdue":
        lead_in = (
            f"{subscriber.full_name}, your installment for {group.title} cycle {installment.cycle_no} "
            f"was due on {installment.due_date}."
        )
    else:
        lead_in = f"{subscriber.full_name}, your installment for {group.title} cycle {installment.cycle_no} is due today."
    return (
        f"{lead_in} Outstanding amount: {money_int(installment.balance_amount)}. "
        f"Please make the payment at the earliest."
    )


def notify_payment_reminders(db: Session, *, as_of: date | None = None) -> list[Notification]:
    reminder_date = as_of or utcnow().date()
    installments = db.scalars(
        select(Installment)
        .join(GroupMembership, GroupMembership.id == Installment.membership_id)
        .join(ChitGroup, ChitGroup.id == Installment.group_id)
        .where(
            ChitGroup.status == "active",
            GroupMembership.membership_status == "active",
            Installment.status != "paid",
            func.coalesce(Installment.balance_amount, 0) > 0,
            Installment.due_date <= reminder_date,
        )
        .order_by(Installment.due_date.asc(), Installment.cycle_no.asc(), Installment.id.asc())
    ).all()

    if not installments:
        return []

    group_ids = sorted({installment.group_id for installment in installments})
    membership_ids = sorted({installment.membership_id for installment in installments})
    groups = {
        group.id: group
        for group in db.scalars(select(ChitGroup).where(ChitGroup.id.in_(group_ids))).all()
    }
    memberships = {
        membership.id: membership
        for membership in db.scalars(select(GroupMembership).where(GroupMembership.id.in_(membership_ids))).all()
    }
    subscriber_ids = sorted(
        {membership.subscriber_id for membership in memberships.values() if membership is not None}
    )
    subscribers = {
        subscriber.id: subscriber
        for subscriber in db.scalars(select(Subscriber).where(Subscriber.id.in_(subscriber_ids))).all()
    }

    notifications: list[Notification] = []
    for installment in installments:
        reminder_kind = _payment_reminder_kind(installment, reminder_date)
        if reminder_kind is None:
            continue

        group = groups.get(installment.group_id)
        membership = memberships.get(installment.membership_id)
        subscriber = subscribers.get(membership.subscriber_id) if membership is not None else None
        if group is None or membership is None or subscriber is None:
            continue

        title = _payment_reminder_title(group, installment, reminder_kind)
        message = _payment_reminder_message(group, subscriber, installment, reminder_kind)
        reminder_notifications: list[Notification] = []
        _append_channel_notifications(
            reminder_notifications,
            db=db,
            user_id=subscriber.user_id,
            owner_id=group.owner_id,
            title=title,
            message=message,
        )
        notifications.extend(reminder_notifications)

    stage_notification_dispatch(db, notifications)
    return notifications


def notify_password_reset_requested(db: Session, *, user) -> list[Notification]:
    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    owner_id = owner.id if owner is not None else subscriber.owner_id if subscriber is not None else None

    notifications: list[Notification] = []
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=user.id,
        owner_id=owner_id,
        title="Password reset requested",
        message="A password reset was requested for your account.",
    )

    stage_notification_dispatch(db, notifications)
    return notifications


def notify_password_reset_confirmed(db: Session, *, user) -> list[Notification]:
    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    owner_id = owner.id if owner is not None else subscriber.owner_id if subscriber is not None else None

    notifications: list[Notification] = []
    _append_channel_notifications(
        notifications,
        db=db,
        user_id=user.id,
        owner_id=owner_id,
        title="Password reset completed",
        message="Your password was changed successfully.",
    )

    stage_notification_dispatch(db, notifications)
    return notifications
