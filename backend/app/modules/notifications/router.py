from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.notifications.schemas import NotificationResponse
from app.modules.notifications.service import list_notifications, mark_notification_as_read

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse] | PaginatedResponse[NotificationResponse])
async def list_notifications_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_notifications(db, current_user, page=page, page_size=pageSize)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read_endpoint(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return mark_notification_as_read(db, notification_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found") from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Notification does not belong to the current owner or subscriber",
        ) from exc
