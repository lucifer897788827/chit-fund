from __future__ import annotations

import time

from app.core.redis import redis_client

ADMIN_USERS_CACHE_TTL_SECONDS = 15
ADMIN_USERS_VERSION_KEY = "admin_users:version"


def _current_cache_version() -> str:
    version = redis_client.get(ADMIN_USERS_VERSION_KEY)
    if version is None:
        version = "1"
        redis_client.set(ADMIN_USERS_VERSION_KEY, version, ex=86400)
    return str(version)


def admin_users_cache_key(page: int, limit: int, lite: bool) -> str:
    version = _current_cache_version()
    return f"admin_users:{version}:{page}:{limit}:{int(lite)}"


def admin_user_detail_cache_key(user_id: int, lite: bool) -> str:
    version = _current_cache_version()
    return f"admin_user_detail:{version}:{user_id}:{int(lite)}"


def load_admin_users_cache(page: int, limit: int, lite: bool):
    return redis_client.get(admin_users_cache_key(page, limit, lite))


def store_admin_users_cache(page: int, limit: int, lite: bool, payload) -> bool:
    return redis_client.set(
        admin_users_cache_key(page, limit, lite),
        payload,
        ex=ADMIN_USERS_CACHE_TTL_SECONDS,
    )


def load_admin_user_detail_cache(user_id: int, lite: bool):
    return redis_client.get(admin_user_detail_cache_key(user_id, lite))


def store_admin_user_detail_cache(user_id: int, lite: bool, payload) -> bool:
    return redis_client.set(
        admin_user_detail_cache_key(user_id, lite),
        payload,
        ex=ADMIN_USERS_CACHE_TTL_SECONDS,
    )


def invalidate_admin_users_cache() -> bool:
    return redis_client.set(
        ADMIN_USERS_VERSION_KEY,
        str(time.time_ns()),
        ex=86400,
    )
