from __future__ import annotations

import importlib

import redis


class _FakeRedis:
    def __init__(self, *args, **kwargs):
        self.store = {}
        self.ping_calls = 0

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self):
        self.ping_calls += 1
        return True


def test_redis_client_uses_connection_pool_and_round_trips_values(monkeypatch):
    pool_args = {}
    fake_client = _FakeRedis()

    def fake_from_url(url, **kwargs):
        pool_args["url"] = url
        pool_args["kwargs"] = kwargs
        return object()

    def fake_redis(*, connection_pool, decode_responses=True):
        return fake_client

    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "redis_url", "redis://cache.example:6379/3")
    monkeypatch.setattr(config_module.settings, "redis_max_connections", 24)
    monkeypatch.setattr(config_module.settings, "redis_socket_connect_timeout_seconds", 2.5)
    monkeypatch.setattr(config_module.settings, "redis_socket_timeout_seconds", 3.5)
    monkeypatch.setattr(config_module.settings, "redis_health_check_interval_seconds", 11)
    monkeypatch.setattr(redis.ConnectionPool, "from_url", fake_from_url)
    monkeypatch.setattr(redis, "Redis", fake_redis)

    redis_core = importlib.reload(importlib.import_module("app.core.redis"))

    assert pool_args["url"] == "redis://cache.example:6379/3"
    assert pool_args["kwargs"]["decode_responses"] is True
    assert pool_args["kwargs"]["health_check_interval"] == 11
    assert pool_args["kwargs"]["max_connections"] == 24
    assert pool_args["kwargs"]["retry_on_timeout"] is True
    assert pool_args["kwargs"]["socket_connect_timeout"] == 2.5
    assert pool_args["kwargs"]["socket_keepalive"] is True
    assert pool_args["kwargs"]["socket_timeout"] == 3.5
    assert redis_core.redis_client.set("greeting", "hello") is True
    assert redis_core.redis_client.set("payload", {"count": 2, "enabled": True}) is True
    assert redis_core.redis_client.get("greeting") == "hello"
    assert redis_core.redis_client.get("payload") == {"count": 2, "enabled": True}
    assert redis_core.redis_client.ping() is True
    assert redis_core.redis_client.health()["ok"] is True


def test_redis_client_falls_back_when_redis_errors(monkeypatch):
    class _BrokenRedis:
        def get(self, key):
            raise redis.exceptions.ConnectionError("down")

        def set(self, key, value, ex=None):
            raise redis.exceptions.ConnectionError("down")

        def delete(self, key):
            raise redis.exceptions.ConnectionError("down")

        def ping(self):
            raise redis.exceptions.ConnectionError("down")

    def fake_from_url(url, **kwargs):
        return object()

    def fake_redis(*, connection_pool, decode_responses=True):
        return _BrokenRedis()

    monkeypatch.setattr(redis.ConnectionPool, "from_url", fake_from_url)
    monkeypatch.setattr(redis, "Redis", fake_redis)

    redis_core = importlib.reload(importlib.import_module("app.core.redis"))

    assert redis_core.redis_client.get("missing") is None
    assert redis_core.redis_client.set("key", {"x": 1}) is False
    assert redis_core.redis_client.delete("key") is False
    assert redis_core.redis_client.ping() is False
    assert redis_core.redis_client.health()["ok"] is False
