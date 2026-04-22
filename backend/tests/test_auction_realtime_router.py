from datetime import date, datetime, timezone

import asyncio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Subscriber, User
from app.modules.auctions.realtime_router import _relay_remote_auction_events
from app.modules.auctions.realtime_service import INSTANCE_ID


def _seed_auction_session(db_session):
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    user = db_session.scalar(select(User).where(User.phone == "8888888888"))
    assert subscriber is not None
    assert user is not None

    group = ChitGroup(
        owner_id=1,
        group_code="WS-001",
        title="Realtime Chit",
        chit_value=100000,
        installment_amount=5000,
        member_count=10,
        cycle_count=5,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
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

    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 5, 10, 12, 1, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=user.id,
    )
    db_session.add(session)
    db_session.commit()
    return session.id


def test_auction_websocket_sends_initial_snapshot(app, db_session):
    session_id = _seed_auction_session(db_session)
    token = create_access_token("2")

    client = TestClient(app)
    with client.websocket_connect(
        f"/ws/auction/{session_id}",
        subprotocols=["access-token", token],
    ) as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "auction.snapshot"
    assert payload["sessionId"] == session_id
    assert payload["room"]["sessionId"] == session_id
    assert payload["room"]["status"] == "open"
    assert payload["auth"]["userId"] == 2


def test_auction_websocket_rejects_missing_token(app):
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/auction/999"):
            pass


def test_relay_remote_auction_events_ignores_local_events_and_forwards_remote_events(monkeypatch):
    stop_event = asyncio.Event()
    forwarded = []
    closed = []
    pubsub = object()
    events = iter(
        [
            {
                "eventType": "auction.bid.placed",
                "sessionId": 123,
                "payload": {"bidId": 1},
                "sourceInstanceId": INSTANCE_ID,
            },
            {
                "eventType": "auction.bid.placed",
                "sessionId": 123,
                "payload": {"bidId": 2},
                "sourceInstanceId": "remote-instance",
            },
        ]
    )

    monkeypatch.setattr(
        "app.modules.auctions.realtime_router.subscribe_to_all_auction_events",
        lambda: pubsub,
    )
    monkeypatch.setattr(
        "app.modules.auctions.realtime_router.read_next_auction_event",
        lambda _pubsub, _timeout, _raise_on_error: next(events, None),
    )
    monkeypatch.setattr(
        "app.modules.auctions.realtime_router.close_auction_event_listener",
        lambda _pubsub: closed.append("closed"),
    )

    async def fake_broadcast(session_id, payload):
        forwarded.append((session_id, payload))
        stop_event.set()

    monkeypatch.setattr("app.modules.auctions.realtime_router.connection_manager.broadcast", fake_broadcast)

    asyncio.run(
        asyncio.wait_for(
            _relay_remote_auction_events(123, stop_event=stop_event, poll_timeout=0.01, retry_delay=0),
            timeout=1,
        )
    )

    assert forwarded == [
        (123, {"eventType": "auction.bid.placed", "sessionId": 123, "payload": {"bidId": 2}, "sourceInstanceId": "remote-instance"})
    ]
    assert closed == ["closed"]


def test_relay_remote_auction_events_recovers_after_listener_failure(monkeypatch):
    stop_event = asyncio.Event()
    forwarded = []
    closed = []
    pubsub_one = object()
    pubsub_two = object()
    subscribe_calls = iter([pubsub_one, pubsub_two])
    read_calls = {"count": 0}

    monkeypatch.setattr(
        "app.modules.auctions.realtime_router.subscribe_to_all_auction_events",
        lambda: next(subscribe_calls, None),
    )

    def fake_read_next(pubsub, _timeout, _raise_on_error):
        read_calls["count"] += 1
        if pubsub is pubsub_one:
            raise RuntimeError("listener dropped")
        return {
            "eventType": "auction.finalized",
            "sessionId": 456,
            "payload": {"sessionId": 456},
            "sourceInstanceId": "remote-instance",
        }

    monkeypatch.setattr("app.modules.auctions.realtime_router.read_next_auction_event", fake_read_next)
    monkeypatch.setattr(
        "app.modules.auctions.realtime_router.close_auction_event_listener",
        lambda pubsub: closed.append(pubsub),
    )

    async def fake_broadcast(session_id, payload):
        forwarded.append((session_id, payload))
        stop_event.set()

    monkeypatch.setattr("app.modules.auctions.realtime_router.connection_manager.broadcast", fake_broadcast)

    asyncio.run(
        asyncio.wait_for(
            _relay_remote_auction_events(456, stop_event=stop_event, poll_timeout=0.01, retry_delay=0),
            timeout=1,
        )
    )

    assert read_calls["count"] >= 2
    assert closed == [pubsub_one, pubsub_two]
    assert forwarded == [
        (456, {"eventType": "auction.finalized", "sessionId": 456, "payload": {"sessionId": 456}, "sourceInstanceId": "remote-instance"})
    ]
