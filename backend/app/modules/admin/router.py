from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.admin.schemas import (
    AdminAuctionSummaryResponse,
    AdminBulkDeactivateRequest,
    AdminBulkDeactivateResponse,
    AdminDefaulterInsightResponse,
    AdminGroupDetailResponse,
    AdminGroupSummaryResponse,
    AdminInsightsSummaryResponse,
    AdminMessageCreate,
    AdminMessageResponse,
    AdminPaymentSummaryResponse,
    AdminUserActivateResponse,
    AdminUserDetailResponse,
    AdminUserDeactivateResponse,
    AdminUserSummaryResponse,
)
from app.modules.admin.service import (
    activate_admin_user,
    build_admin_system_health,
    create_admin_message,
    deactivate_admin_user,
    bulk_deactivate_admin_users,
    get_active_admin_message,
    get_admin_group,
    get_admin_user,
    list_admin_auctions,
    list_admin_defaulters,
    list_admin_groups,
    list_admin_payments,
    list_admin_summary,
    list_finalize_jobs,
    list_admin_users,
)

router = APIRouter(tags=["admin"])


@router.get("/api/admin/finalize-jobs")
async def list_finalize_jobs_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_finalize_jobs(db, current_user)


@router.get("/api/admin/system-health")
async def system_health_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return build_admin_system_health(db, current_user)


@router.get("/api/admin/messages", response_model=AdminMessageResponse | None)
async def get_admin_message_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_active_admin_message(db, current_user)


@router.post("/api/admin/messages", response_model=AdminMessageResponse, status_code=201)
async def create_admin_message_endpoint(
    payload: AdminMessageCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_admin_message(db, payload, current_user)


@router.get("/api/admin/users", response_model=PaginatedResponse[AdminUserSummaryResponse])
async def list_admin_users_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    lite: bool = Query(False),
    role: str | None = Query(None),
    active: bool | None = Query(None),
    search: str | None = Query(None),
    scoreRange: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_users(
        db,
        current_user,
        page=page,
        limit=limit,
        lite=lite,
        role=role,
        active=active,
        search=search,
        score_range=scoreRange,
    )


@router.get("/api/admin/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_admin_user_endpoint(
    user_id: int,
    lite: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_admin_user(db, user_id, current_user, lite=lite)


@router.post("/api/admin/users/{user_id}/deactivate", response_model=AdminUserDeactivateResponse)
async def deactivate_admin_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return deactivate_admin_user(db, user_id, current_user)


@router.post("/api/admin/users/{user_id}/activate", response_model=AdminUserActivateResponse)
async def activate_admin_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return activate_admin_user(db, user_id, current_user)


@router.post("/api/admin/users/bulk-deactivate", response_model=AdminBulkDeactivateResponse)
async def bulk_deactivate_admin_users_endpoint(
    payload: AdminBulkDeactivateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return bulk_deactivate_admin_users(db, payload.userIds, current_user)


@router.get("/api/admin/groups", response_model=list[AdminGroupSummaryResponse])
async def list_admin_groups_endpoint(
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_groups(db, current_user, status=status, search=search)


@router.get("/api/admin/groups/{group_id}", response_model=AdminGroupDetailResponse)
async def get_admin_group_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_admin_group(db, group_id, current_user)


@router.get("/api/admin/auctions", response_model=list[AdminAuctionSummaryResponse])
async def list_admin_auctions_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_auctions(db, current_user)


@router.get("/api/admin/payments", response_model=list[AdminPaymentSummaryResponse])
async def list_admin_payments_endpoint(
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_payments(db, current_user, status=status, search=search)


@router.get("/api/admin/insights/defaulters", response_model=list[AdminDefaulterInsightResponse])
async def list_admin_defaulters_endpoint(
    threshold: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_defaulters(db, current_user, threshold=threshold)


@router.get("/api/admin/insights/summary", response_model=AdminInsightsSummaryResponse)
async def list_admin_summary_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_summary(db, current_user)
