from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.core.redis import redis_client


_CHANNEL_PREFIX = "auction:realtime:session:"
_CHANNEL_PATTERN = f"{_CHANNEL_PREFIX}*"
INSTANCE_ID = uuid4().hex


def auction_event_channel(session_id: int) -> str:
    return f"{_CHANNEL_PREFIX}{session_id}"


def _redis_backend():
    try:
        backend = getattr(redis_client, "client", redis_client)
    except Exception:  # pragma: no cover - import-safe fallback
        return None
    return backend


def _encode_event(session_id: int, event_type: str, payload: dict[str, Any]) -> str:
    event = {
        "eventType": event_type,
        "sessionId": session_id,
        "payload": payload,
    }
    return json.dumps(event, separators=(",", ":"))


def _build_event(session_id: int, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventType": event_type,
        "sessionId": session_id,
        "payload": payload,
        "sourceInstanceId": INSTANCE_ID,
    }


def publish_auction_event(session_id: int, event_type: str, payload: dict[str, Any]) -> bool:
    event = _build_event(session_id, event_type, payload)
    backend = _redis_backend()
    if backend is None or not hasattr(backend, "publish"):
        return False

    try:
        backend.publish(auction_event_channel(session_id), json.dumps(event, separators=(",", ":")))
    except Exception:  # pragma: no cover - fail open when Redis is unavailable
        return False
    return True


def publish_auction_bid_event(session_id: int, payload: dict[str, Any]) -> bool:
    return publish_auction_event(session_id, "auction.bid.placed", payload)


def publish_auction_finalize_event(session_id: int, payload: dict[str, Any]) -> bool:
    return publish_auction_event(session_id, "auction.finalized", payload)


def publish_auction_snapshot_event(session_id: int, payload: dict[str, Any]) -> bool:
    return publish_auction_event(session_id, "auction.snapshot", payload)


def subscribe_to_auction_events(session_id: int):
    backend = _redis_backend()
    if backend is None or not hasattr(backend, "pubsub"):
        return None

    try:
        pubsub = backend.pubsub()
        pubsub.subscribe(auction_event_channel(session_id))
        return pubsub
    except Exception:  # pragma: no cover - fail open when Redis is unavailable
        return None


def subscribe_to_all_auction_events():
    backend = _redis_backend()
    if backend is None or not hasattr(backend, "pubsub"):
        return None

    try:
        pubsub = backend.pubsub()
        pubsub.psubscribe(_CHANNEL_PATTERN)
        return pubsub
    except Exception:  # pragma: no cover - fail open when Redis is unavailable
        return None


def close_auction_event_listener(pubsub: Any) -> None:
    if pubsub is None:
        return

    close = getattr(pubsub, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # pragma: no cover - fail open on shutdown
            return


def _decode_pubsub_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    if message.get("type") not in {"message", "pmessage"}:
        return None

    data = message.get("data")
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if isinstance(data, str):
        try:
            decoded = json.loads(data)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, dict):
            return decoded
        return None
    if isinstance(data, dict):
        return data
    return None


def _session_id_from_channel(channel: Any) -> int | None:
    if isinstance(channel, bytes):
        channel = channel.decode("utf-8")
    if not isinstance(channel, str) or not channel.startswith(_CHANNEL_PREFIX):
        return None
    try:
        return int(channel.removeprefix(_CHANNEL_PREFIX))
    except ValueError:
        return None


def read_next_auction_event(
    pubsub: Any,
    timeout: float = 1.0,
    raise_on_error: bool = False,
) -> dict[str, Any] | None:
    if pubsub is None:
        return None

    get_message = getattr(pubsub, "get_message", None)
    if not callable(get_message):
        return None

    try:
        message = get_message(ignore_subscribe_messages=True, timeout=timeout)
    except Exception:  # pragma: no cover - fail open when listener is unavailable
        if raise_on_error:
            raise
        return None

    decoded = _decode_pubsub_message(message)
    if decoded is None:
        return None

    if decoded.get("sessionId") is None:
        session_id = _session_id_from_channel(message.get("channel") if isinstance(message, dict) else None)
        if session_id is not None:
            decoded["sessionId"] = session_id

    return decoded
