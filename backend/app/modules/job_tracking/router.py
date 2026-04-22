from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user, require_owner
from app.modules.job_tracking.schemas import JobRunResponse
from app.modules.job_tracking.service import get_job_run, list_job_runs, serialize_job_run

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRunResponse] | PaginatedResponse[JobRunResponse])
async def list_job_runs_endpoint(
    taskName: str | None = None,
    status: str | None = None,
    limit: int = Query(25, ge=1),
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_job_runs(db, current_user, task_name=taskName, status=status, limit=limit, page=page, page_size=pageSize)


@router.get("/{job_run_id}", response_model=JobRunResponse)
async def get_job_run_endpoint(
    job_run_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    owner = require_owner(current_user)
    job_run = get_job_run(db, job_run_id)
    if job_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job run not found")
    if job_run.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another owner's job run")
    return serialize_job_run(job_run)
