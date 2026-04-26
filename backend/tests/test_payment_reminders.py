from datetime import date

from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.support import Notification
from app.models.user import Subscriber
from app.tasks.notification_tasks import queue_payment_reminders


def _seed_payment_reminder_case(db_session):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None

    group = ChitGroup(
        owner_id=1,
        group_code="REM-001",
        title="Reminder Group",
        chit_value=120000,
        installment_amount=1000,
        member_count=12,
        cycle_count=4,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
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

    db_session.add_all(
        [
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=1,
                due_date=date(2026, 4, 21),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=1000,
                status="pending",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=2,
                due_date=date(2026, 4, 18),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=250,
                balance_amount=750,
                status="partial",
            ),
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=3,
                due_date=date(2026, 4, 22),
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
                due_date=date(2026, 4, 20),
                due_amount=1000,
                penalty_amount=0,
                paid_amount=1000,
                balance_amount=0,
                status="paid",
            ),
        ]
    )
    db_session.commit()
    return group, subscriber


def test_queue_payment_reminders_creates_due_and_overdue_notifications(app, db_session):
    group, subscriber = _seed_payment_reminder_case(db_session)

    result = queue_payment_reminders(as_of="2026-04-21")

    assert len(result) == 4
    assert {entry["channel"] for entry in result} == {"in_app", "email"}
    assert {entry["title"] for entry in result} == {
        "Due payment reminder for Reminder Group cycle 1",
        "Overdue payment reminder for Reminder Group cycle 2",
    }

    notifications = db_session.scalars(
        select(Notification).where(Notification.owner_id == group.owner_id)
    ).all()

    assert len(notifications) == 4
    assert {notification.channel for notification in notifications} == {"in_app", "email"}
    assert {notification.status for notification in notifications} == {"pending"}
    assert sum(1 for notification in notifications if notification.title.startswith("Due payment reminder")) == 2
    assert sum(1 for notification in notifications if notification.title.startswith("Overdue payment reminder")) == 2
    assert all(subscriber.full_name in notification.message for notification in notifications)


def test_queue_payment_reminders_is_idempotent_for_repeated_runs(app, db_session):
    group, _subscriber = _seed_payment_reminder_case(db_session)

    first_run = queue_payment_reminders(as_of="2026-04-21")
    second_run = queue_payment_reminders(as_of="2026-04-21")

    assert len(first_run) == 4
    assert second_run == []

    notifications = db_session.scalars(
        select(Notification).where(Notification.owner_id == group.owner_id)
    ).all()
    assert len(notifications) == 4
