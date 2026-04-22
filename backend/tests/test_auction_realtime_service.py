import json

from app.modules.auctions.realtime_service import (
    auction_event_channel,
    read_next_auction_event,
    publish_auction_bid_event,
    publish_auction_finalize_event,
    publish_auction_snapshot_event,
    publish_auction_event,
    subscribe_to_auction_events,
)


class FakePubSub:
    def __init__(self, messages=None):
        self.subscribed = []
        self._messages = list(messages or [])

    def subscribe(self, channel):
        self.subscribed.append(channel)

    def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if not self._messages:
            return None
        return self._messages.pop(0)


class FakeRedisClient:
    def __init__(self, *, fail_publish=False, fail_pubsub=False, messages=None):
        self.fail_publish = fail_publish
        self.fail_pubsub = fail_pubsub
        self.published = []
        self.pubsub_instance = FakePubSub(messages)

    @property
    def client(self):
        return self

    def publish(self, channel, message):
        if self.fail_publish:
            raise RuntimeError("redis down")
        self.published.append((channel, message))
        return 1

    def pubsub(self):
        if self.fail_pubsub:
            raise RuntimeError("redis down")
        return self.pubsub_instance


def test_auction_event_channel_is_session_scoped():
    assert auction_event_channel(42) == "auction:realtime:session:42"


def test_publish_and_stream_auction_events_round_trip(monkeypatch):
    backend = FakeRedisClient(
        messages=[
            {
                "type": "message",
                "channel": "auction:realtime:session:42",
                "data": json.dumps(
                    {"eventType": "auction.bid.placed", "sessionId": 42, "payload": {"bidId": 7}}
                ),
            }
        ],
    )
    monkeypatch.setattr("app.modules.auctions.realtime_service.redis_client", backend)

    bid_payload = {"bidId": 7, "bidAmount": 12000}
    finalize_payload = {"sessionStatus": "finalized"}
    snapshot_payload = {"sessionId": 42, "status": "open"}

    assert publish_auction_bid_event(42, bid_payload) is True
    assert publish_auction_finalize_event(42, finalize_payload) is True
    assert publish_auction_snapshot_event(42, snapshot_payload) is True
    assert [channel for channel, _ in backend.published] == ["auction:realtime:session:42"] * 3

    bid_event = json.loads(backend.published[0][1])
    finalize_event = json.loads(backend.published[1][1])
    snapshot_event = json.loads(backend.published[2][1])

    assert bid_event["eventType"] == "auction.bid.placed"
    assert bid_event["sessionId"] == 42
    assert bid_event["payload"] == bid_payload
    assert isinstance(bid_event["sourceInstanceId"], str) and bid_event["sourceInstanceId"]

    assert finalize_event["eventType"] == "auction.finalized"
    assert finalize_event["sessionId"] == 42
    assert finalize_event["payload"] == finalize_payload
    assert isinstance(finalize_event["sourceInstanceId"], str) and finalize_event["sourceInstanceId"]

    assert snapshot_event["eventType"] == "auction.snapshot"
    assert snapshot_event["sessionId"] == 42
    assert snapshot_event["payload"] == snapshot_payload
    assert isinstance(snapshot_event["sourceInstanceId"], str) and snapshot_event["sourceInstanceId"]

    pubsub = subscribe_to_auction_events(42)
    assert pubsub is backend.pubsub_instance
    assert pubsub.subscribed == ["auction:realtime:session:42"]

    event = read_next_auction_event(pubsub)
    assert event == {
        "eventType": "auction.bid.placed",
        "sessionId": 42,
        "payload": {"bidId": 7},
    }


def test_auction_realtime_helpers_fail_open_when_redis_is_unavailable(monkeypatch):
    backend = FakeRedisClient(fail_publish=True, fail_pubsub=True)
    monkeypatch.setattr("app.modules.auctions.realtime_service.redis_client", backend)

    assert publish_auction_event(99, "snapshot", {"sessionId": 99}) is False
    assert subscribe_to_auction_events(99) is None
    assert read_next_auction_event(None) is None
