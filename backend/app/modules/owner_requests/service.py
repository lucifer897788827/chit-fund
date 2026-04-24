from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_admin, require_subscriber
from app.models.user import Owner, OwnerRequest, Subscriber, User


def _requester_name(current_user: CurrentUser) -> str:
    if current_user.subscriber is not None and current_user.subscriber.full_name:
        return current_user.subscriber.full_name
    return current_user.user.email or current_user.user.phone


def _serialize_owner_request(db: Session, owner_request: OwnerRequest) -> dict:
    user = db.scalar(select(User).where(User.id == owner_request.user_id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == owner_request.user_id))
    owner = db.scalar(select(Owner).where(Owner.user_id == owner_request.user_id))
    phone = None
    email = None
    if user is not None:
        phone = user.phone
        email = user.email

    return {
        "id": owner_request.id,
        "userId": owner_request.user_id,
        "status": owner_request.status,
        "createdAt": owner_request.created_at,
        "requesterName": subscriber.full_name if subscriber is not None else (user.email or user.phone if user is not None else None),
        "phone": phone,
        "email": email,
        "ownerId": owner.id if owner is not None else None,
    }


def create_owner_request(db: Session, current_user: CurrentUser) -> dict:
    require_subscriber(current_user)
    if current_user.owner is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner profile already exists")

    existing_pending = db.scalar(
        select(OwnerRequest).where(
            OwnerRequest.user_id == current_user.user.id,
            OwnerRequest.status == "pending",
        )
    )
    if existing_pending is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner request is already pending")

    owner_request = OwnerRequest(
        user_id=current_user.user.id,
        status="pending",
    )
    db.add(owner_request)
    db.commit()
    db.refresh(owner_request)

    return {
        "id": owner_request.id,
        "userId": current_user.user.id,
        "status": owner_request.status,
        "createdAt": owner_request.created_at,
        "requesterName": _requester_name(current_user),
        "phone": current_user.user.phone,
        "email": current_user.user.email,
        "ownerId": None,
    }


def list_owner_requests(db: Session, current_user: CurrentUser) -> list[dict]:
    require_admin(current_user)
    requests = db.scalars(
        select(OwnerRequest).order_by(OwnerRequest.created_at.desc(), OwnerRequest.id.desc())
    ).all()
    return [_serialize_owner_request(db, owner_request) for owner_request in requests]


def _resolve_owner_request(db: Session, request_id: int) -> OwnerRequest:
    owner_request = db.scalar(select(OwnerRequest).where(OwnerRequest.id == request_id))
    if owner_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner request not found")
    return owner_request


def approve_owner_request(db: Session, request_id: int, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    owner_request = _resolve_owner_request(db, request_id)
    if owner_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner request is not pending")

    user = db.scalar(select(User).where(User.id == owner_request.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    owner_created = owner is None
    if owner is None:
        subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
        display_name = (
            subscriber.full_name
            if subscriber is not None and subscriber.full_name
            else user.email or user.phone
        )
        business_name = f"{display_name} Chits"
        owner = Owner(
            user_id=user.id,
            display_name=display_name,
            business_name=business_name,
            city=None,
            state=None,
            status="active",
        )
        db.add(owner)
        db.flush()

    owner_request.status = "approved"
    if user.role != "admin":
        user.role = "chit_owner"
    db.commit()
    db.refresh(owner_request)

    payload = _serialize_owner_request(db, owner_request)
    payload["ownerCreated"] = owner_created
    return payload


def reject_owner_request(db: Session, request_id: int, current_user: CurrentUser) -> dict:
    require_admin(current_user)
    owner_request = _resolve_owner_request(db, request_id)
    if owner_request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner request is not pending")

    owner_request.status = "rejected"
    db.commit()
    db.refresh(owner_request)

    payload = _serialize_owner_request(db, owner_request)
    payload["ownerCreated"] = False
    return payload
