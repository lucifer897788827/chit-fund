from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Owner, Subscriber, User
from app.modules.groups.schemas import MembershipCreate
from app.modules.groups.membership_validation import validate_membership_creation


def _current_owner_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id)) if user else None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id)) if user else None
    assert user is not None
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _other_owner(db_session, phone: str, email: str) -> Owner:
    user = User(
        email=email,
        phone=phone,
        password_hash="",
        role="chit_owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    owner = Owner(
        user_id=user.id,
        display_name="Other Owner",
        business_name="Other Owner Chits",
        city="Bengaluru",
        state="Karnataka",
        status="active",
    )
    db_session.add(owner)
    db_session.flush()
    return owner


def _group(db_session, owner_id: int, group_code: str) -> ChitGroup:
    group = ChitGroup(
        owner_id=owner_id,
        group_code=group_code,
        title=f"{group_code} Title",
        chit_value=10000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.flush()
    return group


def _subscriber(
    db_session,
    *,
    owner_id: int,
    phone: str,
    email: str,
    full_name: str,
    status: str = "active",
) -> Subscriber:
    user = User(
        email=email,
        phone=phone,
        password_hash="",
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=owner_id,
        full_name=full_name,
        phone=phone,
        email=email,
        status=status,
    )
    db_session.add(subscriber)
    db_session.flush()
    return subscriber


def _membership(db_session, *, group_id: int, subscriber_id: int, member_no: int) -> GroupMembership:
    membership = GroupMembership(
        group_id=group_id,
        subscriber_id=subscriber_id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.flush()
    return membership


def test_validate_membership_creation_rejects_group_owner_mismatch(app, db_session):
    current_user = _current_owner_user(db_session)
    other_owner = _other_owner(db_session, phone="6666666666", email="other-owner@example.com")
    group = _group(db_session, owner_id=other_owner.id, group_code="MEM-OWN-001")

    payload = MembershipCreate(subscriberId=1, memberNo=1)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 403


def test_validate_membership_creation_rejects_subscriber_owner_mismatch(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-002")
    other_owner = _other_owner(db_session, phone="6666666667", email="other-owner-2@example.com")
    subscriber = _subscriber(
        db_session,
        owner_id=other_owner.id,
        phone="6777777777",
        email="other-subscriber@example.com",
        full_name="Other Subscriber",
    )

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=1)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 400


def test_validate_membership_creation_rejects_inactive_subscriber(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-003")
    subscriber = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777778",
        email="inactive-subscriber@example.com",
        full_name="Inactive Subscriber",
        status="inactive",
    )

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=1)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 400


def test_validate_membership_creation_rejects_duplicate_member_no(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-004")
    subscriber_one = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777779",
        email="member-one@example.com",
        full_name="Member One",
    )
    subscriber_two = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777780",
        email="member-two@example.com",
        full_name="Member Two",
    )
    _membership(db_session, group_id=group.id, subscriber_id=subscriber_one.id, member_no=1)

    payload = MembershipCreate(subscriberId=subscriber_two.id, memberNo=1)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 409


def test_validate_membership_creation_allows_additional_slots_for_existing_subscriber(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-005")
    subscriber = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777781",
        email="member-three@example.com",
        full_name="Member Three",
    )
    membership = _membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=2)
    validated = validate_membership_creation(db_session, group.id, payload, current_user)

    assert validated.existing_membership is not None
    assert validated.existing_membership.id == membership.id
    assert validated.requested_slot_count == 1


def test_validate_membership_creation_rejects_existing_slot_number_for_same_subscriber(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-005B")
    subscriber = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777781",
        email="member-three@example.com",
        full_name="Member Three",
    )
    membership = _membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)
    db_session.add(
        MembershipSlot(
            user_id=subscriber.user_id,
            group_id=group.id,
            slot_number=membership.member_no,
            has_won=False,
        )
    )
    db_session.flush()

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=1)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Member number is already assigned to this subscriber"


def test_validate_membership_creation_rejects_slot_count_that_overfills_group(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-005C")
    group.member_count = 2
    subscriber = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777781",
        email="member-three@example.com",
        full_name="Member Three",
    )
    _membership(db_session, group_id=group.id, subscriber_id=subscriber.id, member_no=1)

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=2, slotCount=2)

    with pytest.raises(HTTPException) as exc_info:
        validate_membership_creation(db_session, group.id, payload, current_user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Group is full"


def test_validate_membership_creation_returns_context_for_valid_membership(app, db_session):
    current_user = _current_owner_user(db_session)
    group = _group(db_session, owner_id=current_user.owner.id, group_code="MEM-OWN-006")
    subscriber = _subscriber(
        db_session,
        owner_id=current_user.owner.id,
        phone="6777777782",
        email="member-four@example.com",
        full_name="Member Four",
    )

    payload = MembershipCreate(subscriberId=subscriber.id, memberNo=1)
    validated = validate_membership_creation(db_session, group.id, payload, current_user)

    assert validated.owner.id == current_user.owner.id
    assert validated.group.id == group.id
    assert validated.subscriber.id == subscriber.id
