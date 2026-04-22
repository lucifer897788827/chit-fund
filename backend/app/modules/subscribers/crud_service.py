from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_owner
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.models.user import Subscriber
from app.models.user import User


def _serialize_subscriber(subscriber: Subscriber) -> dict:
    return {
        "id": subscriber.id,
        "ownerId": subscriber.owner_id,
        "fullName": subscriber.full_name,
        "phone": subscriber.phone,
        "email": subscriber.email,
        "status": subscriber.status,
    }


def list_subscribers(
    db: Session,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)
    statement = select(Subscriber).where(Subscriber.owner_id == owner.id).order_by(Subscriber.id.asc())
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        subscribers = db.scalars(statement).all()
        return [_serialize_subscriber(subscriber) for subscriber in subscribers]

    total_count = count_statement(db, statement)
    subscribers = db.scalars(apply_pagination(statement, pagination)).all()
    return build_paginated_response([_serialize_subscriber(subscriber) for subscriber in subscribers], pagination, total_count)


def update_subscriber(db: Session, subscriber_id: int, payload, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == subscriber_id))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    if subscriber.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's subscriber")

    payload_owner_id = getattr(payload, "ownerId", None)
    if payload_owner_id is not None and payload_owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's subscriber")

    if hasattr(payload, "fullName") and payload.fullName is not None:
        subscriber.full_name = payload.fullName
    if hasattr(payload, "phone") and payload.phone is not None:
        subscriber.phone = payload.phone
        user = db.get(User, subscriber.user_id)
        if user is not None:
            user.phone = payload.phone
    if hasattr(payload, "email"):
        subscriber.email = payload.email
        user = db.get(User, subscriber.user_id)
        if user is not None:
            user.email = payload.email

    subscriber.owner_id = owner.id
    db.commit()
    db.refresh(subscriber)
    return _serialize_subscriber(subscriber)


def soft_delete_subscriber(db: Session, subscriber_id: int, current_user: CurrentUser) -> dict:
    owner = require_owner(current_user)
    subscriber = db.scalar(select(Subscriber).where(Subscriber.id == subscriber_id))
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    if subscriber.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage another owner's subscriber")

    subscriber.status = "deleted"
    db.commit()
    db.refresh(subscriber)
    return _serialize_subscriber(subscriber)
