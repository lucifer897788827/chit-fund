from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.admin.schemas import AdminMessageCreate, AdminMessageResponse, AdminUserSummaryResponse
from app.modules.admin.service import (
    build_admin_system_health,
    create_admin_message,
    get_active_admin_message,
    get_admin_user,
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


@router.get("/api/admin/users", response_model=list[AdminUserSummaryResponse])
async def list_admin_users_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_admin_users(db, current_user)


@router.get("/api/admin/users/{user_id}", response_model=AdminUserSummaryResponse)
async def get_admin_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_admin_user(db, user_id, current_user)
