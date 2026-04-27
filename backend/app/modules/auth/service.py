from __future__ import annotations

import hashlib
import logging
import secrets
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import load_only
from sqlalchemy.orm import Session
from time import perf_counter, time

from app.core.security import (
    ACCESS_TOKEN_EXPIRES_MINUTES,
    create_access_token,
    create_password_reset_token,
    hash_password_reset_token,
    hash_password,
    verify_password,
)
from app.core.time import utcnow
from app.models.auth import RefreshToken
from app.core.config import settings
from app.core.redis import redis_client
from app.models.user import Owner, Subscriber, User
from app.core.security import CurrentUser
from app.modules.notifications.service import (
    dispatch_staged_notifications,
    notify_password_reset_confirmed,
    notify_password_reset_requested,
)
from app.modules.subscribers.auth_service import create_subscriber_user
from app.modules.subscribers.validation import validate_subscriber_creation

LOGIN_LOCKOUT_PREFIX = "auth:login:lockout"
LOGIN_FAILURE_PREFIX = "auth:login:failures"
_clock = time
REFRESH_TOKEN_EXPIRES_DAYS = 30
REFRESH_TOKEN_CLEANUP_RETENTION_DAYS = 7
REFRESH_TOKEN_BYTES = 48
PASSWORD_RESET_ERROR = "Invalid or expired password reset token"
logger = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    return phone.strip()


def _lockout_key(phone: str) -> str:
    return f"{LOGIN_LOCKOUT_PREFIX}:{_normalize_phone(phone)}"


def _failure_key(phone: str) -> str:
    return f"{LOGIN_FAILURE_PREFIX}:{_normalize_phone(phone)}"


def _current_timestamp() -> int:
    return int(_clock())


def _remaining_lockout_seconds(phone: str) -> int:
    raw_value = redis_client.get(_lockout_key(phone))
    if raw_value is None:
        return 0

    try:
        unlock_at = int(raw_value)
    except (TypeError, ValueError):
        redis_client.delete(_lockout_key(phone))
        return 0

    remaining = unlock_at - _current_timestamp()
    if remaining <= 0:
        redis_client.delete(_lockout_key(phone))
        return 0

    return remaining


def _maybe_raise_lockout(phone: str) -> None:
    remaining = _remaining_lockout_seconds(phone)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(remaining)},
        )


def _reset_login_attempts(phone: str) -> None:
    redis_client.delete(_failure_key(phone), _lockout_key(phone))


def _register_failed_login(phone: str) -> None:
    max_attempts = max(0, int(settings.auth_login_max_attempts))
    attempt_window = max(0, int(settings.auth_login_attempt_window_seconds))
    cooldown_seconds = max(0, int(settings.auth_login_cooldown_seconds))

    if max_attempts <= 0 or attempt_window <= 0 or cooldown_seconds <= 0:
        return

    failure_key = _failure_key(phone)
    current_failures = redis_client.get(failure_key)
    try:
        failure_count = int(current_failures or 0) + 1
    except (TypeError, ValueError):
        failure_count = 1

    redis_client.set(failure_key, failure_count, ex=attempt_window)

    if failure_count < max_attempts:
        return

    unlock_at = _current_timestamp() + cooldown_seconds
    redis_client.set(_lockout_key(phone), unlock_at, ex=cooldown_seconds)
    redis_client.delete(failure_key)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Please try again later.",
        headers={"Retry-After": str(cooldown_seconds)},
    )


def _refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _issue_refresh_token(db: Session, user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    expires_at = utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
    refresh_record = RefreshToken(
        user_id=user_id,
        token_hash=_refresh_token_hash(token),
        expires_at=expires_at,
    )
    db.add(refresh_record)
    db.flush()
    return token, expires_at


def _revoke_user_refresh_tokens(db: Session, user_id: int, *, exclude_token_hash: str | None = None) -> None:
    active_tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    now = utcnow()
    for token in active_tokens:
        if exclude_token_hash and token.token_hash == exclude_token_hash:
            continue
        token.revoked_at = now
        token.updated_at = now


def _cleanup_refresh_tokens(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=REFRESH_TOKEN_CLEANUP_RETENTION_DAYS)
    result = db.execute(
        delete(RefreshToken)
        .where(
            (RefreshToken.revoked_at.is_not(None) & (RefreshToken.revoked_at < cutoff))
            | (RefreshToken.expires_at < cutoff)
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _record_timing(timings: dict[str, float], key: str, started_at: float) -> None:
    timings[key] = _elapsed_ms(started_at)


def _log_login_performance(*, phone: str, success: bool, timings: dict[str, float], user_id: int | None = None) -> None:
    extra = {
        "event": "auth.login.performance",
        "success": success,
        "user_id": user_id,
        "lockout_check_ms": timings.get("lockout_check_ms", 0.0),
        "db_fetch_ms": timings.get("db_fetch_ms", 0.0),
        "hash_verify_ms": timings.get("hash_verify_ms", 0.0),
        "refresh_token_ms": timings.get("refresh_token_ms", 0.0),
        "profile_fetch_ms": timings.get("profile_fetch_ms", 0.0),
        "jwt_ms": timings.get("jwt_ms", 0.0),
        "commit_ms": timings.get("commit_ms", 0.0),
        "total_ms": timings.get("total_ms", 0.0),
    }
    logger.info("auth.login.performance", extra=extra)


def _build_token_response(
    db: Session,
    user: User,
    refresh_token: str,
    refresh_token_expires_at: datetime,
    timings: dict[str, float] | None = None,
) -> dict:
    profile_started_at = perf_counter()
    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    if timings is not None:
        _record_timing(timings, "profile_fetch_ms", profile_started_at)
    roles = _resolve_roles(user=user, owner=owner, subscriber=subscriber)
    primary_role = _derive_primary_role(user=user, roles=roles)
    jwt_started_at = perf_counter()
    access_token = create_access_token(str(user.id))
    if timings is not None:
        _record_timing(timings, "jwt_ms", jwt_started_at)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "refresh_token_expires_at": refresh_token_expires_at,
        "access_token_expires_in": ACCESS_TOKEN_EXPIRES_MINUTES * 60,
        "refresh_token_expires_in": REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60,
        "role": primary_role,
        "roles": roles,
        "owner_id": owner.id if owner else None,
        "subscriber_id": subscriber.id if subscriber else None,
        "has_subscriber_profile": subscriber is not None,
        "user": {
            "id": user.id,
            "roles": roles,
        },
    }


def _resolve_roles(*, user: User, owner: Owner | None, subscriber: Subscriber | None) -> list[str]:
    roles: list[str] = []
    if subscriber is not None:
        roles.append("subscriber")
    if owner is not None:
        roles.append("owner")
    if user.role == "admin":
        roles.append("admin")
    return roles


def _derive_primary_role(*, user: User, roles: list[str]) -> str:
    if "admin" in roles:
        return "admin"
    if "owner" in roles:
        return "chit_owner"
    if "subscriber" in roles:
        return "subscriber"
    return user.role


def build_auth_me_response(current_user: CurrentUser) -> dict:
    roles = _resolve_roles(
        user=current_user.user,
        owner=current_user.owner,
        subscriber=current_user.subscriber,
    )
    return {
        "role": _derive_primary_role(user=current_user.user, roles=roles),
        "roles": roles,
        "owner_id": current_user.owner.id if current_user.owner else None,
        "subscriber_id": current_user.subscriber.id if current_user.subscriber else None,
        "has_subscriber_profile": current_user.subscriber is not None,
        "user": {
            "id": current_user.user.id,
            "roles": roles,
        },
    }


def _normalize_signup_payload(payload) -> SimpleNamespace:
    full_name = payload.fullName.strip()
    phone = payload.phone.strip()
    email = payload.email.strip() if isinstance(payload.email, str) else None
    if email == "":
        email = None

    if not full_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Full name is required")
    if not phone:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Phone is required")
    if not isinstance(payload.password, str) or not payload.password.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password is required")

    return SimpleNamespace(
        ownerId=None,
        fullName=full_name,
        phone=phone,
        email=email,
        password=payload.password,
    )


def login_user(db: Session, phone: str, password: str) -> dict:
    timings: dict[str, float] = {}
    total_started_at = perf_counter()
    normalized_phone = _normalize_phone(phone)
    lockout_started_at = perf_counter()
    _maybe_raise_lockout(normalized_phone)
    _record_timing(timings, "lockout_check_ms", lockout_started_at)

    db_fetch_started_at = perf_counter()
    user = db.scalar(
        select(User)
        .options(
            load_only(
                User.id,
                User.phone,
                User.password_hash,
                User.role,
                User.is_active,
                User.last_login_at,
                User.updated_at,
            )
        )
        .where(User.phone == normalized_phone)
    )
    _record_timing(timings, "db_fetch_ms", db_fetch_started_at)
    if user is None:
        timings["total_ms"] = _elapsed_ms(total_started_at)
        _log_login_performance(phone=normalized_phone, success=False, timings=timings)
        _register_failed_login(normalized_phone)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password",
        )

    hash_started_at = perf_counter()
    password_valid = verify_password(password, user.password_hash)
    _record_timing(timings, "hash_verify_ms", hash_started_at)
    if not password_valid:
        timings["total_ms"] = _elapsed_ms(total_started_at)
        _log_login_performance(phone=normalized_phone, success=False, timings=timings, user_id=user.id)
        _register_failed_login(normalized_phone)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password",
        )

    _reset_login_attempts(normalized_phone)
    user.last_login_at = utcnow()
    user.updated_at = utcnow()
    user_id = user.id
    refresh_started_at = perf_counter()
    refresh_token, refresh_token_expires_at = _issue_refresh_token(db, user_id)
    _record_timing(timings, "refresh_token_ms", refresh_started_at)
    _cleanup_refresh_tokens(db)
    response = _build_token_response(db, user, refresh_token, refresh_token_expires_at, timings=timings)
    commit_started_at = perf_counter()
    db.commit()
    _record_timing(timings, "commit_ms", commit_started_at)
    timings["total_ms"] = _elapsed_ms(total_started_at)
    _log_login_performance(phone=normalized_phone, success=True, timings=timings, user_id=user_id)
    return response


def signup_user(db: Session, payload) -> dict:
    normalized_payload = _normalize_signup_payload(payload)
    validate_subscriber_creation(db, normalized_payload)

    user = create_subscriber_user(normalized_payload)
    db.add(user)
    db.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=None,
        full_name=normalized_payload.fullName,
        phone=normalized_payload.phone,
        email=normalized_payload.email,
        status="active",
    )
    db.add(subscriber)
    refresh_token, refresh_token_expires_at = _issue_refresh_token(db, user.id)
    _cleanup_refresh_tokens(db)
    db.commit()
    return _build_token_response(db, user, refresh_token, refresh_token_expires_at)


def refresh_session(db: Session, refresh_token: str) -> dict:
    refresh_token_hash = _refresh_token_hash(refresh_token)
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == refresh_token_hash))
    if (
        record is None
        or record.revoked_at is not None
        or _as_utc(record.expires_at) <= utcnow()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.scalar(select(User).where(User.id == record.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    record.revoked_at = utcnow()
    record.updated_at = utcnow()
    new_refresh_token, refresh_token_expires_at = _issue_refresh_token(db, user.id)
    _cleanup_refresh_tokens(db)
    db.commit()
    return _build_token_response(db, user, new_refresh_token, refresh_token_expires_at)


def logout_user(db: Session, current_user: CurrentUser, refresh_token: str | None = None) -> None:
    now = utcnow()
    if refresh_token:
        token_hash = _refresh_token_hash(refresh_token)
        record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if record is not None:
            if record.user_id != current_user.user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot revoke another user's session")
            record.revoked_at = now
            record.updated_at = now
    _cleanup_refresh_tokens(db)
    db.commit()


def request_password_reset(db: Session, phone: str) -> dict:
    normalized_phone = _normalize_phone(phone)
    user = db.scalar(select(User).where(User.phone == normalized_phone))
    message = "If an account exists, a password reset token has been generated."
    if user is None:
        return {"message": message, "reset_token": None, "reset_token_expires_at": None}

    reset_token, expires_at = create_password_reset_token()
    user.password_reset_token_hash = hash_password_reset_token(reset_token)
    user.password_reset_token_expires_at = expires_at
    user.updated_at = utcnow()
    notify_password_reset_requested(db, user=user)
    _cleanup_refresh_tokens(db)
    db.commit()
    response_token = reset_token if settings.is_dev_profile else None
    response_expires_at = expires_at if settings.is_dev_profile else None
    try:
        dispatch_staged_notifications(db)
    except Exception:
        pass
    return {
        "message": message,
        "reset_token": response_token,
        "reset_token_expires_at": response_expires_at,
    }


def confirm_password_reset(db: Session, token: str, new_password: str) -> dict:
    if not isinstance(new_password, str) or len(new_password.strip()) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be at least 8 characters",
        )

    token_hash = hash_password_reset_token(token)
    user = db.scalar(
        select(User).where(
            User.password_reset_token_hash == token_hash,
            User.password_reset_token_expires_at.is_not(None),
        )
    )
    if user is None or _as_utc(user.password_reset_token_expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PASSWORD_RESET_ERROR)

    user.password_hash = hash_password(new_password)
    user.password_reset_token_hash = None
    user.password_reset_token_expires_at = None
    user.updated_at = utcnow()
    _revoke_user_refresh_tokens(db, user.id)
    notify_password_reset_confirmed(db, user=user)
    _cleanup_refresh_tokens(db)
    db.commit()
    try:
        dispatch_staged_notifications(db)
    except Exception:
        pass
    return {"message": "Password has been reset"}
