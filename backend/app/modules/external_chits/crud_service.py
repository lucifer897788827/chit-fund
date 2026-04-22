from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.core.time import utcnow
from app.models.external import ExternalChit
from app.models.user import Subscriber
from app.modules.external_chits.serializers import serialize_external_chit


def _get_subscriber_for_current_user(db: Session, current_user: CurrentUser, subscriber_id: int) -> Subscriber:
    subscriber = db.get(Subscriber, subscriber_id)
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    if current_user.owner is not None:
        owner = require_owner(current_user)
        if subscriber.owner_id != owner.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot manage another owner's subscriber",
            )
        return subscriber

    current_subscriber = require_subscriber(current_user)
    if subscriber.id != current_subscriber.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's data",
        )
    return subscriber


def _get_chit_for_current_user(db: Session, current_user: CurrentUser, chit_id: int) -> ExternalChit:
    external_chit = db.get(ExternalChit, chit_id)
    if external_chit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit not found")

    _get_subscriber_for_current_user(db, current_user, external_chit.subscriber_id)
    return external_chit


def list_external_chits(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    _get_subscriber_for_current_user(db, current_user, subscriber_id)
    statement = select(ExternalChit).where(ExternalChit.subscriber_id == subscriber_id).order_by(ExternalChit.id.asc())
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        chits = db.scalars(statement).all()
        return [serialize_external_chit(chit) for chit in chits]

    total_count = count_statement(db, statement)
    chits = db.scalars(apply_pagination(statement, pagination)).all()
    return build_paginated_response([serialize_external_chit(chit) for chit in chits], pagination, total_count)


def create_external_chit(db: Session, payload, current_user: CurrentUser) -> dict:
    subscriber = _get_subscriber_for_current_user(db, current_user, payload.subscriberId)

    external_chit = ExternalChit(
        subscriber_id=subscriber.id,
        user_id=subscriber.user_id,
        title=payload.title,
        name=getattr(payload, "name", None) or payload.title,
        organizer_name=payload.organizerName,
        chit_value=payload.chitValue,
        installment_amount=payload.installmentAmount,
        monthly_installment=getattr(payload, "monthlyInstallment", None),
        total_members=getattr(payload, "totalMembers", None),
        total_months=getattr(payload, "totalMonths", None),
        user_slots=getattr(payload, "userSlots", None),
        first_month_organizer=bool(getattr(payload, "firstMonthOrganizer", False)),
        cycle_frequency=payload.cycleFrequency,
        start_date=payload.startDate,
        end_date=getattr(payload, "endDate", None),
        notes=getattr(payload, "notes", None),
        status=getattr(payload, "status", "active") or "active",
    )
    db.add(external_chit)
    db.commit()
    db.refresh(external_chit)
    return serialize_external_chit(external_chit)


def update_external_chit(db: Session, chit_id: int, payload, current_user: CurrentUser) -> dict:
    external_chit = _get_chit_for_current_user(db, current_user, chit_id)

    payload_subscriber_id = getattr(payload, "subscriberId", None)
    if payload_subscriber_id is not None and payload_subscriber_id != external_chit.subscriber_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage another owner's subscriber",
        )

    if hasattr(payload, "title") and payload.title is not None:
        external_chit.title = payload.title
    if hasattr(payload, "name"):
        external_chit.name = payload.name or external_chit.title
    if hasattr(payload, "organizerName") and payload.organizerName is not None:
        external_chit.organizer_name = payload.organizerName
    if hasattr(payload, "chitValue") and payload.chitValue is not None:
        external_chit.chit_value = payload.chitValue
    if hasattr(payload, "installmentAmount") and payload.installmentAmount is not None:
        external_chit.installment_amount = payload.installmentAmount
    if hasattr(payload, "monthlyInstallment") and payload.monthlyInstallment is not None:
        external_chit.monthly_installment = payload.monthlyInstallment
    if hasattr(payload, "totalMembers") and payload.totalMembers is not None:
        external_chit.total_members = payload.totalMembers
    if hasattr(payload, "totalMonths") and payload.totalMonths is not None:
        external_chit.total_months = payload.totalMonths
    if hasattr(payload, "userSlots") and payload.userSlots is not None:
        external_chit.user_slots = payload.userSlots
    if hasattr(payload, "firstMonthOrganizer") and payload.firstMonthOrganizer is not None:
        external_chit.first_month_organizer = bool(payload.firstMonthOrganizer)
    if hasattr(payload, "cycleFrequency") and payload.cycleFrequency is not None:
        external_chit.cycle_frequency = payload.cycleFrequency
    if hasattr(payload, "startDate") and payload.startDate is not None:
        external_chit.start_date = payload.startDate
    if hasattr(payload, "endDate"):
        external_chit.end_date = payload.endDate
    if hasattr(payload, "notes"):
        external_chit.notes = payload.notes
    if hasattr(payload, "status") and payload.status is not None:
        external_chit.status = payload.status

    external_chit.updated_at = utcnow()
    db.commit()
    db.refresh(external_chit)
    return serialize_external_chit(external_chit)


def delete_external_chit(db: Session, chit_id: int, current_user: CurrentUser) -> dict:
    external_chit = _get_chit_for_current_user(db, current_user, chit_id)
    external_chit.status = "deleted"
    external_chit.updated_at = utcnow()
    db.commit()
    db.refresh(external_chit)
    return serialize_external_chit(external_chit)
