from __future__ import annotations

import json
from time import monotonic
from typing import Any

import redis

from app.core.config import settings


class RedisClient:
    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.redis_url
        self._unavailable_until = 0.0
        self._outage_backoff_seconds = 30.0
        pool_kwargs = {
            "decode_responses": True,
            "health_check_interval": settings.redis_health_check_interval_seconds,
            "retry_on_timeout": True,
            "socket_connect_timeout": settings.redis_socket_connect_timeout_seconds,
            "socket_keepalive": True,
            "socket_timeout": settings.redis_socket_timeout_seconds,
        }
        if settings.redis_max_connections is not None:
            pool_kwargs["max_connections"] = settings.redis_max_connections

        self._connection_pool = redis.ConnectionPool.from_url(
            self._redis_url,
            **pool_kwargs,
        )
        self._client = redis.Redis(
            connection_pool=self._connection_pool,
            decode_responses=True,
        )

    def _is_temporarily_unavailable(self) -> bool:
        return monotonic() < self._unavailable_until

    def _mark_unavailable(self) -> None:
        self._unavailable_until = monotonic() + self._outage_backoff_seconds

    def _mark_available(self) -> None:
        self._unavailable_until = 0.0

    @property
    def connection_pool(self):
        return self._connection_pool

    @property
    def client(self):
        return self._client

    def _encode_value(self, value: Any) -> Any:
        if isinstance(value, (str, bytes)):
            return value
        return f"json:{json.dumps(value, separators=(',', ':'))}"

    def _decode_value(self, value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, bytes):
            value = value.decode("utf-8")

        if isinstance(value, str) and value.startswith("json:"):
            try:
                return json.loads(value[5:])
            except json.JSONDecodeError:
                return value

        return value

    def get(self, _key):
        if self._is_temporarily_unavailable():
            return None
        try:
            value = self._client.get(_key)
        except Exception:
            self._mark_unavailable()
            return None
        self._mark_available()
        return self._decode_value(value)

    def set(self, _key, _value, ex=None):
        if self._is_temporarily_unavailable():
            return False
        try:
            result = bool(self._client.set(_key, self._encode_value(_value), ex=ex))
        except Exception:
            self._mark_unavailable()
            return False
        self._mark_available()
        return result

    def delete(self, *_keys):
        if not _keys:
            return False
        if self._is_temporarily_unavailable():
            return False
        try:
            result = bool(self._client.delete(*_keys))
        except Exception:
            self._mark_unavailable()
            return False
        self._mark_available()
        return result

    def ping(self) -> bool:
        try:
            result = bool(self._client.ping())
        except Exception:
            self._mark_unavailable()
            return False
        self._mark_available()
        return result

    def health(self) -> dict[str, Any]:
        healthy = self.ping()
        return {
            "ok": healthy,
            "redis_url": self._redis_url,
            "connected": healthy,
        }


redis_client = RedisClient()
