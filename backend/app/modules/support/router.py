from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.support.schemas import JobRunResponse
from app.modules.support.service import list_job_runs

router = APIRouter(prefix="/api/support", tags=["support"])


@router.get("/jobs", response_model=list[JobRunResponse] | PaginatedResponse[JobRunResponse])
async def list_job_runs_endpoint(
    status: str | None = None,
    taskName: str | None = None,
    limit: int = Query(50, ge=1),
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_job_runs(
        db,
        current_user,
        status=status,
        task_name=taskName,
        limit=limit,
        page=page,
        page_size=pageSize,
    )
