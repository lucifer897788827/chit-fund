import json

from app.modules.auctions.cache_service import (
    cache_auction_room_state,
    cache_auction_session,
    cache_group,
    cache_membership,
    get_cached_auction_room_state,
    get_cached_auction_session,
    get_cached_group,
    get_cached_membership,
)


class DummyRedis:
    def __init__(self):
        self.calls = []
        self.values = {}
        self.fail_on_set = False
        self.fail_on_get = False

    def set(self, key, value, ex=None):
        self.calls.append(("set", key, value, ex))
        if self.fail_on_set:
            raise RuntimeError("redis down")
        self.values[key] = value
        return True

    def get(self, key):
        self.calls.append(("get", key))
        if self.fail_on_get:
            raise RuntimeError("redis down")
        return self.values.get(key)


def test_cache_group_uses_ttl_and_round_trips_payload(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr("app.modules.auctions.cache_service.redis_client", redis)

    payload = {"groupId": 7, "groupCode": "GRP-001", "status": "active"}

    assert cache_group(7, payload) is True
    assert redis.calls[0][0] == "set"
    assert redis.calls[0][1] == "auction:group:7"
    assert json.loads(redis.calls[0][2]) == payload
    assert redis.calls[0][3] == 300
    assert get_cached_group(7) == payload


def test_cache_membership_and_session_use_distinct_keys(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr("app.modules.auctions.cache_service.redis_client", redis)

    membership_payload = {"membershipId": 9, "canBid": True}
    session_payload = {"sessionId": 4, "status": "open"}

    assert cache_membership(9, membership_payload) is True
    assert cache_auction_session(4, session_payload) is True

    assert redis.calls[0][1] == "auction:membership:9"
    assert redis.calls[0][3] == 300
    assert redis.calls[1][1] == "auction:session:4"
    assert redis.calls[1][3] == 30
    assert get_cached_membership(9) == membership_payload
    assert get_cached_auction_session(4) == session_payload


def test_cache_room_state_fails_open_on_redis_error(monkeypatch):
    redis = DummyRedis()
    redis.fail_on_set = True
    monkeypatch.setattr("app.modules.auctions.cache_service.redis_client", redis)

    room_state = {"sessionId": 10, "status": "open"}

    assert cache_auction_room_state(10, room_state) is False
    assert get_cached_auction_room_state(10) is None
