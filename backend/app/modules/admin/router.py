from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.admin.service import build_admin_system_health, list_finalize_jobs

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
