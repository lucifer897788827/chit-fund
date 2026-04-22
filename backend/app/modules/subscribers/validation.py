from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Subscriber, User


@dataclass(slots=True)
class ValidatedSubscriberCreateContext:
    owner_id: int | None
    full_name: str
    phone: str
    email: str | None


def validate_subscriber_creation(db: Session, payload) -> ValidatedSubscriberCreateContext:
    duplicate_phone = db.scalar(select(User.id).where(User.phone == payload.phone))
    if duplicate_phone is None:
        duplicate_phone = db.scalar(select(Subscriber.id).where(Subscriber.phone == payload.phone))
    if duplicate_phone is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already exists")

    if payload.email is not None:
        duplicate_email = db.scalar(select(User.id).where(User.email == payload.email))
        if duplicate_email is None:
            duplicate_email = db.scalar(select(Subscriber.id).where(Subscriber.email == payload.email))
        if duplicate_email is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    return ValidatedSubscriberCreateContext(
        owner_id=getattr(payload, "ownerId", None),
        full_name=payload.fullName,
        phone=payload.phone,
        email=payload.email,
    )
