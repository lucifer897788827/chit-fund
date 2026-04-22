from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.reporting.schemas import OwnerActivityItem, OwnerAuditLogItem, OwnerDashboardResponse, OwnerPayoutSummary
from app.modules.reporting.service import (
    get_owner_dashboard_report,
    list_owner_activity,
    list_owner_audit_logs,
    list_owner_payouts,
)

router = APIRouter(prefix="/api/reporting/owner", tags=["reporting"])


@router.get("/dashboard", response_model=OwnerDashboardResponse)
async def get_owner_dashboard_endpoint(
    activityLimit: int = Query(10, ge=1),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_owner_dashboard_report(db, current_user, activity_limit=activityLimit)


@router.get("/activity", response_model=list[OwnerActivityItem] | PaginatedResponse[OwnerActivityItem])
async def list_owner_activity_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_activity(db, current_user, page=page, page_size=pageSize)


@router.get("/audit-logs", response_model=list[OwnerAuditLogItem] | PaginatedResponse[OwnerAuditLogItem])
async def list_owner_audit_logs_endpoint(
    action: str | None = None,
    entityType: str | None = None,
    entityId: str | None = None,
    actorId: int | None = None,
    limit: int = Query(50, ge=1),
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_audit_logs(
        db,
        current_user,
        action=action,
        entity_type=entityType,
        entity_id=entityId,
        actor_user_id=actorId,
        limit=limit,
        page=page,
        page_size=pageSize,
    )


@router.get("/payouts", response_model=list[OwnerPayoutSummary] | PaginatedResponse[OwnerPayoutSummary])
async def list_owner_payouts_endpoint(
    subscriberId: int | None = None,
    groupId: int | None = None,
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_payouts(
        db,
        current_user,
        subscriber_id=subscriberId,
        group_id=groupId,
        page=page,
        page_size=pageSize,
    )
