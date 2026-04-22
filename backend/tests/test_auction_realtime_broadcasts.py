import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import CurrentUser
from app.models import Owner, Subscriber, User
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.modules.auctions.service import (
    finalize_auction,
    get_owner_auction_console,
    get_room,
    place_bid,
)


def _owner_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "9999999999"))
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id))
    return CurrentUser(user=user, owner=owner, subscriber=None)


def _subscriber_current_user(db_session) -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return CurrentUser(user=user, owner=None, subscriber=subscriber)


def _seed_live_auction(db_session, *, slot_count: int = 1):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.id == 2))
    group = ChitGroup(
        owner_id=owner.id,
        group_code="AUC-BROADCAST-001",
        title="Auction Broadcast Group",
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

    owner_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=1,
        member_no=1,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    subscriber_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber.id,
        member_no=2,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add_all([owner_membership, subscriber_membership])
    db_session.flush()
    for slot_number in range(1, slot_count + 1):
        db_session.add(
            MembershipSlot(
                user_id=subscriber.user_id,
                group_id=group.id,
                slot_number=slot_number,
                has_won=False,
            )
        )
    db_session.flush()

    current_window_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=current_window_start,
        actual_start_at=current_window_start,
        min_bid_value=0,
        max_bid_value=200000,
        min_increment=1,
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=owner.user_id,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session.id, group.id, owner_membership.id, subscriber_membership.id


def _capture_publisher(monkeypatch):
    calls = []

    def fake_bid_publish(session_id, payload):
        calls.append(("bid", session_id, payload))
        return True

    def fake_finalize_publish(session_id, payload):
        calls.append(("finalize", session_id, payload))
        return True

    monkeypatch.setattr("app.modules.auctions.service.publish_auction_bid_event", fake_bid_publish)
    monkeypatch.setattr("app.modules.auctions.service.publish_auction_finalize_event", fake_finalize_publish)
    return calls


def _without_server_time(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "serverTime"}


def _normalize_payload(payload: dict) -> dict:
    return json.loads(json.dumps(payload, default=str))


def test_place_bid_publishes_room_snapshot(app, db_session, monkeypatch):
    session_id, _group_id, _owner_membership_id, subscriber_membership_id = _seed_live_auction(
        db_session,
        slot_count=2,
    )
    calls = _capture_publisher(monkeypatch)
    current_user = _subscriber_current_user(db_session)

    result = place_bid(
        db_session,
        session_id,
        type("BidPayload", (), {"bidAmount": 12000, "idempotencyKey": "bid-001"})(),
        current_user,
    )

    assert result["accepted"] is True
    assert len(calls) == 1

    event_type, event_session_id, payload = calls[0]
    expected_room = json.loads(json.dumps(get_room(db_session, session_id, current_user), default=str))

    assert event_type == "bid"
    assert event_session_id == session_id
    normalized_payload = _normalize_payload(payload)

    assert normalized_payload["bidId"] == result["bidId"]
    assert _without_server_time(normalized_payload["room"]) == _without_server_time(expected_room)
    assert normalized_payload["room"]["myMembershipId"] == subscriber_membership_id
    assert normalized_payload["room"]["myLastBid"] == 12000
    assert normalized_payload["room"]["minBidValue"] == 0
    assert normalized_payload["room"]["maxBidValue"] == 200000
    assert normalized_payload["room"]["minIncrement"] == 1
    assert normalized_payload["room"]["myBidCount"] == 1
    assert normalized_payload["room"]["myBidLimit"] == 2
    assert normalized_payload["room"]["myRemainingBidCapacity"] == 1
    assert normalized_payload["room"]["mySlotCount"] == 2
    assert normalized_payload["room"]["myWonSlotCount"] == 0
    assert normalized_payload["room"]["myRemainingSlotCount"] == 2
    assert normalized_payload["room"]["slotCount"] == 2
    assert normalized_payload["room"]["wonSlotCount"] == 0
    assert normalized_payload["room"]["remainingSlotCount"] == 2


def test_finalize_auction_publishes_owner_console_snapshot(app, db_session, monkeypatch):
    session_id, group_id, _owner_membership_id, subscriber_membership_id = _seed_live_auction(db_session)
    calls = _capture_publisher(monkeypatch)
    owner_current_user = _owner_current_user(db_session)

    winning_bid = AuctionBid(
        auction_session_id=session_id,
        membership_id=subscriber_membership_id,
        bidder_user_id=2,
        idempotency_key="finalize-001",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 7, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(winning_bid)
    db_session.commit()
    db_session.refresh(winning_bid)

    result = finalize_auction(db_session, session_id, owner_current_user)

    assert result["status"] == "finalized"
    assert len(calls) == 1

    event_type, event_session_id, payload = calls[0]
    expected_console = json.loads(
        json.dumps(get_owner_auction_console(db_session, session_id, owner_current_user), default=str)
    )

    assert event_type == "finalize"
    assert event_session_id == session_id
    normalized_payload = _normalize_payload(payload)

    assert _without_server_time(normalized_payload["console"]) == _without_server_time(expected_console)
    assert normalized_payload["console"]["sessionId"] == session_id
    assert normalized_payload["console"]["status"] == "finalized"
    assert normalized_payload["console"]["finalizationMessage"] == "Auction closed and finalized."
    assert normalized_payload["console"]["winnerMembershipNo"] == 2
