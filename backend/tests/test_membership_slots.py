from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.auction import AuctionBid, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Subscriber, User
from app.modules.auctions.service import persist_auction_result
from app.modules.groups.slot_service import (
    build_membership_slot_summary,
    get_membership_bid_eligibility,
    get_user_available_slot_count,
    get_user_slot_count,
)


def _create_group(db_session, *, code: str = "SLOT-001") -> ChitGroup:
    group = ChitGroup(
        owner_id=1,
        group_code=code,
        title="Slot Group",
        chit_value=250000,
        installment_amount=12500,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        start_date=date(2026, 6, 1),
        first_auction_date=date(2026, 6, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def _create_membership(
    db_session,
    *,
    group_id: int,
    subscriber_id: int,
    member_no: int,
) -> GroupMembership:
    membership = GroupMembership(
        group_id=group_id,
        subscriber_id=subscriber_id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def _create_group_member(db_session, *, group_id: int, member_no: int, suffix: str) -> tuple[User, Subscriber, GroupMembership]:
    user = User(
        email=f"slot-{suffix}@example.com",
        phone=f"755555555{suffix}",
        password_hash="not-used",
        role="subscriber",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=1,
        full_name=f"Slot Member {suffix}",
        phone=user.phone,
        email=user.email,
        status="active",
    )
    db_session.add(subscriber)
    db_session.flush()

    membership = GroupMembership(
        group_id=group_id,
        subscriber_id=subscriber.id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    db_session.refresh(subscriber)
    db_session.refresh(user)
    return user, subscriber, membership


def test_create_membership_endpoint_creates_slot_and_slot_counts(app, db_session):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "SLOT-API-001",
            "title": "Slot Api Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]

    membership_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1},
    )

    assert membership_response.status_code == 201

    slot = db_session.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == group_id,
            MembershipSlot.user_id == 1,
            MembershipSlot.slot_number == 1,
        )
    )

    assert slot is not None
    assert slot.has_won is False
    assert get_user_slot_count(db_session, group_id=group_id, user_id=1) == 1
    assert get_user_available_slot_count(db_session, group_id=group_id, user_id=1) == 1


def test_create_membership_endpoint_supports_multiple_slots_for_one_membership(app, db_session):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "SLOT-API-002",
            "title": "Slot Api Group Two",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]

    membership_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1, "slotCount": 3},
    )

    assert membership_response.status_code == 201
    body = membership_response.json()
    assert body["slotCount"] == 3
    assert body["wonSlotCount"] == 0
    assert body["remainingSlotCount"] == 3
    assert get_user_slot_count(db_session, group_id=group_id, user_id=1) == 3
    assert get_user_available_slot_count(db_session, group_id=group_id, user_id=1) == 3


def test_duplicate_membership_request_adds_slot_to_existing_membership(app, db_session):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    group_response = client.post(
        "/api/groups",
        headers=headers,
        json={
            "ownerId": 1,
            "groupCode": "SLOT-API-003",
            "title": "Slot Api Group Three",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]

    first_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 1},
    )
    second_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=headers,
        json={"subscriberId": 1, "memberNo": 2},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]
    assert second_response.json()["slotCount"] == 2
    assert get_user_slot_count(db_session, group_id=group_id, user_id=1) == 2


def test_legacy_membership_without_slots_uses_backward_compatible_bid_eligibility(app, db_session):
    group = _create_group(db_session, code="SLOT-LEGACY-001")
    membership = _create_membership(db_session, group_id=group.id, subscriber_id=2, member_no=2)

    summary = build_membership_slot_summary(db_session, membership)

    assert summary.total_slots == 1
    assert summary.available_slots == 1
    assert summary.won_slots == 0
    assert get_membership_bid_eligibility(db_session, membership) is True


def test_membership_with_slots_preserves_existing_block_for_unprized_member(app, db_session):
    group = _create_group(db_session, code="SLOT-BLOCK-001")
    membership = _create_membership(db_session, group_id=group.id, subscriber_id=1, member_no=1)
    membership.can_bid = False
    db_session.add(membership)
    db_session.flush()

    db_session.add(
        MembershipSlot(
            user_id=1,
            group_id=group.id,
            slot_number=1,
            has_won=False,
        )
    )
    db_session.commit()

    summary = build_membership_slot_summary(db_session, membership)

    assert summary.total_slots == 1
    assert summary.available_slots == 1
    assert summary.can_bid is False


def test_persist_auction_result_marks_and_reassigns_membership_slots(app, db_session):
    group = _create_group(db_session, code="SLOT-AUC-001")
    first_membership = _create_membership(db_session, group_id=group.id, subscriber_id=1, member_no=1)
    second_user, _second_subscriber, second_membership = _create_group_member(
        db_session,
        group_id=group.id,
        member_no=2,
        suffix="1",
    )

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    first_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=first_membership.id,
        bidder_user_id=1,
        idempotency_key="slot-first",
        bid_amount=10000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 6, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    second_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=second_membership.id,
        bidder_user_id=second_user.id,
        idempotency_key="slot-second",
        bid_amount=11000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 6, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([first_bid, second_bid])
    db_session.commit()
    db_session.refresh(first_bid)
    db_session.refresh(second_bid)

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=first_bid,
        winner_membership_id=first_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 6, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=5000,
        dividend_per_member_amount=500,
        owner_commission_amount=0,
        winner_payout_amount=240000,
    )

    first_slot = db_session.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == 1,
            MembershipSlot.slot_number == 1,
        )
    )
    second_slot = db_session.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == second_user.id,
            MembershipSlot.slot_number == 2,
        )
    )

    assert first_slot is not None
    assert first_slot.has_won is True
    assert second_slot is None

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=second_bid,
        winner_membership_id=second_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 6, 10, 10, 6, tzinfo=timezone.utc),
        dividend_pool_amount=4500,
        dividend_per_member_amount=450,
        owner_commission_amount=0,
        winner_payout_amount=239000,
    )

    db_session.refresh(first_membership)
    db_session.refresh(second_membership)
    first_slot = db_session.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == 1,
            MembershipSlot.slot_number == 1,
        )
    )
    second_slot = db_session.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == second_user.id,
            MembershipSlot.slot_number == 2,
        )
    )

    assert first_slot is not None
    assert second_slot is not None
    assert first_slot.has_won is False
    assert second_slot.has_won is True
    assert first_membership.can_bid is True
    assert first_membership.prized_status == "unprized"
    assert second_membership.can_bid is False
    assert second_membership.prized_status == "prized"


def test_persist_auction_result_rewrite_same_multi_slot_winner_keeps_single_won_slot(app, db_session):
    group = _create_group(db_session, code="SLOT-AUC-002")
    membership = _create_membership(db_session, group_id=group.id, subscriber_id=1, member_no=1)
    db_session.add_all(
        [
            MembershipSlot(user_id=1, group_id=group.id, slot_number=1, has_won=False),
            MembershipSlot(user_id=1, group_id=group.id, slot_number=2, has_won=False),
        ]
    )

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    earlier_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="rewrite-earlier",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 6, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    later_higher_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=1,
        idempotency_key="rewrite-later-higher",
        bid_amount=14000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 6, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([earlier_bid, later_higher_bid])
    db_session.commit()

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=earlier_bid,
        winner_membership_id=membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 6, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=5000,
        dividend_per_member_amount=500,
        owner_commission_amount=0,
        winner_payout_amount=240000,
    )
    persist_auction_result(
        db_session,
        session=session,
        winning_bid=later_higher_bid,
        winner_membership_id=membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 6, 10, 10, 6, tzinfo=timezone.utc),
        dividend_pool_amount=7000,
        dividend_per_member_amount=700,
        owner_commission_amount=0,
        winner_payout_amount=238000,
    )

    slots = db_session.scalars(
        select(MembershipSlot)
        .where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == 1,
        )
        .order_by(MembershipSlot.slot_number.asc())
    ).all()
    db_session.refresh(membership)

    assert [slot.has_won for slot in slots] == [True, False]
    assert membership.prized_status == "prized"
    assert membership.prized_cycle_no == session.cycle_no
    assert membership.can_bid is True


def test_persist_auction_result_reassignment_preserves_earlier_multi_slot_win(app, db_session):
    group = _create_group(db_session, code="SLOT-AUC-003")
    first_membership = _create_membership(db_session, group_id=group.id, subscriber_id=1, member_no=1)
    second_user, _second_subscriber, second_membership = _create_group_member(
        db_session,
        group_id=group.id,
        member_no=2,
        suffix="2",
    )
    db_session.add_all(
        [
            MembershipSlot(user_id=1, group_id=group.id, slot_number=1, has_won=True),
            MembershipSlot(user_id=1, group_id=group.id, slot_number=2, has_won=False),
        ]
    )
    first_membership.prized_status = "prized"
    first_membership.prized_cycle_no = 1
    first_membership.can_bid = True

    session = AuctionSession(
        group_id=group.id,
        cycle_no=2,
        scheduled_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.flush()

    first_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=first_membership.id,
        bidder_user_id=1,
        idempotency_key="rewrite-first-member",
        bid_amount=14000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    second_bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=second_membership.id,
        bidder_user_id=second_user.id,
        idempotency_key="rewrite-second-member",
        bid_amount=15000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 2, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add_all([first_bid, second_bid])
    db_session.commit()

    persist_auction_result(
        db_session,
        session=session,
        winning_bid=first_bid,
        winner_membership_id=first_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 5, tzinfo=timezone.utc),
        dividend_pool_amount=7000,
        dividend_per_member_amount=700,
        owner_commission_amount=0,
        winner_payout_amount=238000,
    )
    persist_auction_result(
        db_session,
        session=session,
        winning_bid=second_bid,
        winner_membership_id=second_membership.id,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 7, 10, 10, 6, tzinfo=timezone.utc),
        dividend_pool_amount=7500,
        dividend_per_member_amount=750,
        owner_commission_amount=0,
        winner_payout_amount=237500,
    )

    first_slots = db_session.scalars(
        select(MembershipSlot)
        .where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == 1,
        )
        .order_by(MembershipSlot.slot_number.asc())
    ).all()
    second_slots = db_session.scalars(
        select(MembershipSlot)
        .where(
            MembershipSlot.group_id == group.id,
            MembershipSlot.user_id == second_user.id,
        )
        .order_by(MembershipSlot.slot_number.asc())
    ).all()
    db_session.refresh(first_membership)
    db_session.refresh(second_membership)

    assert [slot.has_won for slot in first_slots] == [True, False]
    assert [slot.has_won for slot in second_slots] == [True]
    assert first_membership.prized_status == "prized"
    assert first_membership.prized_cycle_no == 2
    assert first_membership.can_bid is True
    assert second_membership.prized_status == "prized"
    assert second_membership.prized_cycle_no == session.cycle_no
    assert second_membership.can_bid is False
