from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.chit import ChitGroup, GroupMembership, Installment, MembershipSlot
from app.models.user import Owner, Subscriber, User
from app.modules.groups.join_service import join_group

pytestmark = pytest.mark.usefixtures("app")


def _subscriber_current_user(db_session, phone: str = "8888888888") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    assert subscriber is not None
    return CurrentUser(user=user, owner=None, subscriber=subscriber)


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    assert user is not None
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id))
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=None)


def _create_group(
    db_session,
    *,
    status: str = "active",
    member_count: int = 3,
    cycle_count: int = 3,
    visibility: str = "public",
):
    owner = db_session.scalar(select(Owner).order_by(Owner.id.asc()))
    assert owner is not None
    group = ChitGroup(
        owner_id=owner.id,
        group_code=f"JOIN-{status}-{member_count}-{cycle_count}",
        title="Join Test Group",
        chit_value=300000,
        installment_amount=15000,
        member_count=member_count,
        cycle_count=cycle_count,
        cycle_frequency="monthly",
        visibility=visibility,
        start_date=date(2026, 6, 1),
        first_auction_date=date(2026, 6, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status=status,
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def test_join_group_requires_subscriber_profile(db_session):
    group = _create_group(db_session)

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 1, "memberNo": 1}, _owner_current_user(db_session))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Subscriber profile required"


def test_join_group_rejects_inactive_group(db_session):
    group = _create_group(db_session, status="draft")

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 1}, _subscriber_current_user(db_session))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Group is not active"


def test_join_group_rejects_private_group_self_join(db_session):
    group = _create_group(db_session, visibility="private")

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 1}, _subscriber_current_user(db_session))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Private groups require owner approval or invite"


def test_join_group_rejects_full_group(db_session):
    group = _create_group(db_session, member_count=2)
    db_session.add(
        GroupMembership(
            group_id=group.id,
            subscriber_id=1,
            member_no=1,
            membership_status="active",
            prized_status="unprized",
            can_bid=True,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        join_group(
            db_session,
            group.id,
            {"subscriberId": 2, "memberNo": 2, "slotCount": 2},
            _subscriber_current_user(db_session),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Group is full"


def test_join_group_rejects_existing_slot_number_for_same_subscriber(db_session):
    group = _create_group(db_session, member_count=3)
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    db_session.add(
        MembershipSlot(
            user_id=2,
            group_id=group.id,
            slot_number=1,
            has_won=False,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 1}, _subscriber_current_user(db_session))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Membership already exists"


def test_join_group_rejects_duplicate_member_number(db_session):
    group = _create_group(db_session, member_count=3)
    db_session.add(
        GroupMembership(
            group_id=group.id,
            subscriber_id=1,
            member_no=1,
            membership_status="active",
            prized_status="unprized",
            can_bid=True,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 1}, _subscriber_current_user(db_session))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Member number is already taken"


def test_join_group_creates_installments_like_membership_creation(db_session):
    group = _create_group(db_session, cycle_count=3)

    result = join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 2}, _subscriber_current_user(db_session))

    membership = db_session.scalar(
        select(GroupMembership).where(GroupMembership.group_id == group.id, GroupMembership.subscriber_id == 2)
    )
    installments = db_session.scalars(
        select(Installment).where(Installment.group_id == group.id, Installment.membership_id == membership.id).order_by(Installment.cycle_no)
    ).all()

    assert result["groupId"] == group.id
    assert result["subscriberId"] == 2
    assert result["memberNo"] == 2
    assert membership is not None
    assert membership.membership_status == "active"
    assert len(installments) == 3
    assert [row.cycle_no for row in installments] == [1, 2, 3]
    assert [row.due_date for row in installments] == [
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
    ]


def test_join_group_skips_elapsed_cycles_for_fresh_memberships(db_session, monkeypatch):
    group = _create_group(db_session, cycle_count=4)
    group.start_date = date(2026, 1, 1)
    group.first_auction_date = date(2026, 1, 10)
    group.current_cycle_no = 2
    db_session.commit()

    monkeypatch.setattr(
        "app.modules.groups.service.utcnow",
        lambda: datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc),
    )

    join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 2}, _subscriber_current_user(db_session))

    membership = db_session.scalar(
        select(GroupMembership).where(GroupMembership.group_id == group.id, GroupMembership.subscriber_id == 2)
    )
    installments = db_session.scalars(
        select(Installment).where(Installment.group_id == group.id, Installment.membership_id == membership.id).order_by(Installment.cycle_no)
    ).all()

    assert [row.cycle_no for row in installments] == [3, 4]
    assert [row.due_date for row in installments] == [date(2026, 3, 1), date(2026, 4, 1)]


def test_join_group_rejects_existing_membership_slot_escalation(db_session):
    group = _create_group(db_session, member_count=4, cycle_count=3)
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    db_session.add(
        MembershipSlot(
            user_id=2,
            group_id=group.id,
            slot_number=1,
            has_won=False,
        )
    )
    for cycle_no, due_date in enumerate([date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)], start=1):
        db_session.add(
            Installment(
                group_id=group.id,
                membership_id=membership.id,
                cycle_no=cycle_no,
                due_date=due_date,
                due_amount=15000,
                penalty_amount=0,
                paid_amount=0,
                balance_amount=15000,
                status="pending",
            )
        )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        join_group(db_session, group.id, {"subscriberId": 2, "memberNo": 2}, _subscriber_current_user(db_session))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Membership already exists"
