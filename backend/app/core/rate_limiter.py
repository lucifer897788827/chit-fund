from __future__ import annotations

from threading import Lock
from time import time

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.redis import redis_client


class RedisFixedWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._clock = time
        self._redis = redis_client
        self._known_keys: set[str] = set()

    def clear(self) -> None:
        with self._lock:
            keys = tuple(self._known_keys)
            self._known_keys.clear()
        if keys:
            delete = getattr(self._redis, "delete", None)
            if callable(delete):
                delete(*keys)
            else:  # pragma: no cover - fallback for the local stub backend
                for key in keys:
                    if hasattr(self._redis, "set"):
                        self._redis.set(key, None)

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        if limit <= 0 or window_seconds <= 0:
            return True, 0

        current_time = self._clock()
        window_index = int(current_time // window_seconds)
        redis_key = self._redis_key(key, window_index)

        with self._lock:
            self._known_keys.add(redis_key)

        count = self._increment(redis_key, window_seconds)
        if count > limit:
            retry_after = max(1, int(window_seconds - (current_time % window_seconds)))
            return False, retry_after

        return True, 0

    def _redis_key(self, key: str, window_index: int) -> str:
        return f"rate_limit:{key}:{window_index}"

    def _increment(self, redis_key: str, window_seconds: int) -> int:
        if hasattr(self._redis, "incr"):
            count = int(self._redis.incr(redis_key))
            if count == 1 and hasattr(self._redis, "expire"):
                self._redis.expire(redis_key, window_seconds)
            return count

        current_value = None
        if hasattr(self._redis, "get"):
            current_value = self._redis.get(redis_key)

        count = int(current_value or 0) + 1
        if hasattr(self._redis, "set"):
            self._redis.set(redis_key, count, ex=window_seconds if count == 1 else None)
        return count


rate_limiter = RedisFixedWindowRateLimiter()


def decode_rate_limit_subject(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except (JWTError, ValueError):
        return None

    subject = payload.get("sub")
    return str(subject) if subject else None


def resolve_rate_limit_identity(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            subject = decode_rate_limit_subject(token)
            if subject:
                return f"user:{subject}"

    client_host = request.client.host if request.client is not None else "unknown"
    return f"ip:{client_host}"


def enforce_request_rate_limit(
    request: Request,
    *,
    family: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int, str]:
    identity = resolve_rate_limit_identity(request)
    allowed, retry_after = rate_limiter.allow(
        f"{identity}:{family}",
        limit,
        window_seconds,
    )
    return allowed, retry_after, identity


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        key = self._build_rate_limit_key(request)
        allowed, retry_after = rate_limiter.allow(
            key,
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    def _build_rate_limit_key(self, request: Request) -> str:
        identity = self._request_identity(request)
        family = self._route_family(request.url.path)
        return f"{identity}:{family}"

    def _request_identity(self, request: Request) -> str:
        return resolve_rate_limit_identity(request)

    def _decode_subject(self, token: str) -> str | None:
        return decode_rate_limit_subject(token)

    def _route_family(self, path: str) -> str:
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) < 2 or segments[0] != "api":
            return path.strip("/") or "root"
        if segments[1] == "auth" and len(segments) > 2:
            return f"auth:{segments[2]}"
        return segments[1]
