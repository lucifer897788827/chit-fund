from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import CurrentUser, hash_password
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Owner, Subscriber, User


def _make_owner(db_session, *, phone: str, email: str, password: str = "ownerpass") -> tuple[User, Owner]:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    owner = Owner(
        user_id=user.id,
        display_name="Owner",
        business_name="Owner Chits",
        city="Chennai",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.flush()
    return user, owner


def _make_subscriber(
    db_session,
    *,
    phone: str,
    email: str,
    owner_id: int,
    password: str = "pass123",
) -> tuple[User, Subscriber]:
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner_id,
        full_name="Subscriber",
        phone=phone,
        email=email,
        status="active",
    )
    db_session.add(subscriber)
    db_session.flush()
    return user, subscriber


def test_owner_can_access_own_subscriber_row(app, db_session):
    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id))
    assert owner_user is not None
    assert owner is not None

    _, target_subscriber = _make_subscriber(
        db_session,
        phone="9000000001",
        email="owned-subscriber@example.com",
        owner_id=owner.id,
    )
    db_session.commit()

    from app.modules.subscribers.access_control import require_owner_subscriber_access

    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=None)
    assert require_owner_subscriber_access(current_user, target_subscriber) is target_subscriber


def test_owner_cannot_access_another_owners_subscriber_row(app, db_session):
    owner_user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == owner_user.id))
    assert owner_user is not None
    assert owner is not None

    other_owner_user, other_owner = _make_owner(
        db_session,
        phone="9999990000",
        email="other-owner@example.com",
    )
    _, target_subscriber = _make_subscriber(
        db_session,
        phone="9000000002",
        email="foreign-subscriber@example.com",
        owner_id=other_owner.id,
    )
    db_session.commit()

    from app.modules.subscribers.access_control import require_owner_subscriber_access

    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=None)
    with pytest.raises(Exception) as exc_info:
        require_owner_subscriber_access(current_user, target_subscriber)

    assert getattr(exc_info.value, "status_code", None) == 403
    assert getattr(exc_info.value, "detail", None) == "Cannot manage another owner's subscriber"


def test_subscriber_can_access_own_profile_row(app, db_session):
    subscriber_user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == subscriber_user.id))
    assert subscriber_user is not None
    assert subscriber is not None

    from app.modules.subscribers.access_control import require_subscriber_profile_access

    current_user = CurrentUser(user=subscriber_user, owner=None, subscriber=subscriber)
    assert require_subscriber_profile_access(current_user, subscriber) is subscriber


def test_subscriber_cannot_access_another_subscriber_profile_row(app, db_session):
    subscriber_user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == subscriber_user.id))
    owner = db_session.scalar(select(Owner).where(Owner.id == subscriber.owner_id))
    assert subscriber_user is not None
    assert subscriber is not None
    assert owner is not None

    _, other_subscriber = _make_subscriber(
        db_session,
        phone="9000000003",
        email="other-profile@example.com",
        owner_id=owner.id,
    )
    db_session.commit()

    from app.modules.subscribers.access_control import require_subscriber_profile_access

    current_user = CurrentUser(user=subscriber_user, owner=None, subscriber=subscriber)
    with pytest.raises(Exception) as exc_info:
        require_subscriber_profile_access(current_user, other_subscriber)

    assert getattr(exc_info.value, "status_code", None) == 403
    assert getattr(exc_info.value, "detail", None) == "Cannot access another subscriber's data"


def test_subscriber_can_access_own_membership_row(app, db_session):
    subscriber_user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == subscriber_user.id))
    owner = db_session.scalar(select(Owner).where(Owner.id == subscriber.owner_id))
    assert subscriber_user is not None
    assert subscriber is not None
    assert owner is not None

    group = ChitGroup(
        owner_id=owner.id,
        group_code="ROW-001",
        title="Access Control Group",
        chit_value=100000,
        installment_amount=5000,
        member_count=10,
        cycle_count=10,
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
        member_no=4,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.commit()

    from app.modules.subscribers.access_control import require_subscriber_membership_access

    current_user = CurrentUser(user=subscriber_user, owner=None, subscriber=subscriber)
    assert require_subscriber_membership_access(current_user, membership) is membership


def test_subscriber_cannot_access_another_subscriber_membership_row(app, db_session):
    subscriber_user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == subscriber_user.id))
    owner = db_session.scalar(select(Owner).where(Owner.id == subscriber.owner_id))
    assert subscriber_user is not None
    assert subscriber is not None
    assert owner is not None

    _, other_subscriber = _make_subscriber(
        db_session,
        phone="9000000004",
        email="other-membership@example.com",
        owner_id=owner.id,
    )
    group = ChitGroup(
        owner_id=owner.id,
        group_code="ROW-002",
        title="Access Control Group 2",
        chit_value=100000,
        installment_amount=5000,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 4, 1),
        first_auction_date=date(2026, 4, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    other_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=other_subscriber.id,
        member_no=5,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(other_membership)
    db_session.commit()

    from app.modules.subscribers.access_control import require_subscriber_membership_access

    current_user = CurrentUser(user=subscriber_user, owner=None, subscriber=subscriber)
    with pytest.raises(Exception) as exc_info:
        require_subscriber_membership_access(current_user, other_membership)

    assert getattr(exc_info.value, "status_code", None) == 403
    assert getattr(exc_info.value, "detail", None) == "Cannot access another subscriber's membership"
