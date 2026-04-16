from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import Owner, Subscriber, User


def login_user(db: Session, phone: str, password: str) -> dict:
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password",
        )
    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return {
        "access_token": create_access_token(str(user.id)),
        "token_type": "bearer",
        "role": user.role,
        "owner_id": owner.id if owner else None,
        "subscriber_id": subscriber.id if subscriber else None,
        "has_subscriber_profile": subscriber is not None,
    }
