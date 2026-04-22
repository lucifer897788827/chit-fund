from __future__ import annotations

import json
from typing import Any

from app.core.redis import redis_client

GROUP_CACHE_TTL_SECONDS = 300
MEMBERSHIP_CACHE_TTL_SECONDS = 300
AUCTION_SESSION_CACHE_TTL_SECONDS = 30
AUCTION_ROOM_CACHE_TTL_SECONDS = 30

GROUP_CACHE_KEY_PREFIX = "auction:group"
MEMBERSHIP_CACHE_KEY_PREFIX = "auction:membership"
AUCTION_SESSION_CACHE_KEY_PREFIX = "auction:session"
AUCTION_ROOM_CACHE_KEY_PREFIX = "auction:room"


def _cache_key(prefix: str, entity_id: int) -> str:
    return f"{prefix}:{entity_id}"


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)


def _deserialize_payload(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _set_json_cache(key: str, payload: dict[str, Any], ttl_seconds: int) -> bool:
    try:
        return bool(redis_client.set(key, _serialize_payload(payload), ex=ttl_seconds))
    except Exception:
        return False


def _get_json_cache(key: str) -> dict[str, Any] | None:
    try:
        return _deserialize_payload(redis_client.get(key))
    except Exception:
        return None


def cache_group(group_id: int, payload: dict[str, Any]) -> bool:
    return _set_json_cache(_cache_key(GROUP_CACHE_KEY_PREFIX, group_id), payload, GROUP_CACHE_TTL_SECONDS)


def get_cached_group(group_id: int) -> dict[str, Any] | None:
    return _get_json_cache(_cache_key(GROUP_CACHE_KEY_PREFIX, group_id))


def cache_membership(membership_id: int, payload: dict[str, Any]) -> bool:
    return _set_json_cache(
        _cache_key(MEMBERSHIP_CACHE_KEY_PREFIX, membership_id),
        payload,
        MEMBERSHIP_CACHE_TTL_SECONDS,
    )


def get_cached_membership(membership_id: int) -> dict[str, Any] | None:
    return _get_json_cache(_cache_key(MEMBERSHIP_CACHE_KEY_PREFIX, membership_id))


def cache_auction_session(session_id: int, payload: dict[str, Any]) -> bool:
    return _set_json_cache(
        _cache_key(AUCTION_SESSION_CACHE_KEY_PREFIX, session_id),
        payload,
        AUCTION_SESSION_CACHE_TTL_SECONDS,
    )


def get_cached_auction_session(session_id: int) -> dict[str, Any] | None:
    return _get_json_cache(_cache_key(AUCTION_SESSION_CACHE_KEY_PREFIX, session_id))


def cache_auction_room_state(session_id: int, payload: dict[str, Any]) -> bool:
    return _set_json_cache(_cache_key(AUCTION_ROOM_CACHE_KEY_PREFIX, session_id), payload, AUCTION_ROOM_CACHE_TTL_SECONDS)


def get_cached_auction_room_state(session_id: int) -> dict[str, Any] | None:
    return _get_json_cache(_cache_key(AUCTION_ROOM_CACHE_KEY_PREFIX, session_id))


def cache_room_state(session_id: int, state: dict[str, Any]) -> None:
    cache_auction_room_state(session_id, state)
