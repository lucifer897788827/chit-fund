import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.time import utcnow
from app.models.user import Owner, Subscriber, User

ACCESS_TOKEN_EXPIRES_MINUTES: Final = 15
PASSWORD_RESET_TOKEN_TTL: Final = timedelta(minutes=30)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class CurrentUser:
    user: User
    owner: Owner | None
    subscriber: Subscriber | None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT secret must be configured")
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES))
    payload = {
        "sub": subject,
        "typ": "access",
        "jti": secrets.token_hex(8),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_password_reset_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + PASSWORD_RESET_TOKEN_TTL
    return token, expires_at


def hash_password_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception as exc:  # pragma: no cover - jose raises different subclasses
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    token_type = payload.get("typ")
    if token_type not in (None, "access"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return subject


def _resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id_text = _decode_token(credentials.credentials)
    try:
        user_id = int(user_id_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    row = db.execute(
        select(User, Owner, Subscriber)
        .outerjoin(Owner, Owner.user_id == User.id)
        .outerjoin(Subscriber, Subscriber.user_id == User.id)
        .where(User.id == user_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user, owner, subscriber = row
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    request.state.user_id = user.id
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    current_user = _resolve_current_user(request, credentials, db)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user


def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser | None:
    return _resolve_current_user(request, credentials, db)


def require_owner(current_user: CurrentUser) -> Owner:
    if current_user.owner is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner profile required")
    return current_user.owner


def require_subscriber(current_user: CurrentUser) -> Subscriber:
    if current_user.subscriber is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber profile required")
    return current_user.subscriber


def require_admin(current_user: CurrentUser) -> User:
    if current_user.user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user.user
