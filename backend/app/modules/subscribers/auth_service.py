from fastapi import HTTPException, status

from app.core.security import hash_password
from app.models.user import User


def _get_password(payload) -> str | None:
    password = getattr(payload, "password", None)
    if password is None and isinstance(payload, dict):
        password = payload.get("password")
    return password


def create_subscriber_user(payload) -> User:
    password = _get_password(payload)
    if not isinstance(password, str) or not password.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subscriber password is required")

    return User(
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(password),
        role="subscriber",
        is_active=True,
    )
