from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.subscribers.crud_service import list_subscribers, soft_delete_subscriber, update_subscriber
from app.modules.subscribers.schemas import (
    SubscriberCreate,
    SubscriberDashboardResponse,
    SubscriberResponse,
    SubscriberUpdate,
)
from app.modules.subscribers.service import create_subscriber, get_subscriber_dashboard

router = APIRouter(prefix="/api/subscribers", tags=["subscribers"])


@router.get("", response_model=list[SubscriberResponse] | PaginatedResponse[SubscriberResponse])
async def list_subscribers_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_subscribers(db, current_user, page=page, page_size=pageSize)


@router.post("", response_model=SubscriberResponse, status_code=status.HTTP_201_CREATED)
async def create_subscriber_endpoint(
    payload: SubscriberCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_subscriber(db, payload, current_user)


@router.patch("/{subscriber_id}", response_model=SubscriberResponse)
async def update_subscriber_endpoint(
    subscriber_id: int,
    payload: SubscriberUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return update_subscriber(db, subscriber_id, payload, current_user)


@router.delete("/{subscriber_id}", response_model=SubscriberResponse)
async def delete_subscriber_endpoint(
    subscriber_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return soft_delete_subscriber(db, subscriber_id, current_user)


@router.get("/dashboard", response_model=SubscriberDashboardResponse)
async def get_subscriber_dashboard_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_subscriber_dashboard(db, current_user)
