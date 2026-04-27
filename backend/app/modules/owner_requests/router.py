from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.owner_requests.schemas import (
    OwnerRequestCreate,
    OwnerRequestDecisionResponse,
    OwnerRequestResponse,
)
from app.modules.owner_requests.service import (
    approve_owner_request,
    create_owner_request,
    list_owner_requests,
    reject_owner_request,
)

router = APIRouter(tags=["owner-requests"])


@router.post("/api/owner-requests", response_model=OwnerRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_owner_request_endpoint(
    _payload: OwnerRequestCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_owner_request(db, current_user)


@router.post("/api/users/request-owner", response_model=OwnerRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_owner_request_user_alias_endpoint(
    _payload: OwnerRequestCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_owner_request(db, current_user)


@router.get("/api/admin/owner-requests", response_model=list[OwnerRequestResponse])
async def list_owner_requests_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_requests(db, current_user)


@router.post("/api/admin/owner-requests/{request_id}/approve", response_model=OwnerRequestDecisionResponse)
async def approve_owner_request_endpoint(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return approve_owner_request(db, request_id, current_user)


@router.post("/api/admin/owner-requests/{request_id}/reject", response_model=OwnerRequestDecisionResponse)
async def reject_owner_request_endpoint(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_owner_request(db, request_id, current_user)
