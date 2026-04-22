from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.groups.schemas import (
    AuctionSessionCreate,
    AuctionSessionResponse,
    GroupCreate,
    GroupResponse,
    MembershipCreate,
    MembershipResponse,
)
from app.modules.groups.join_service import join_group
from app.modules.groups.service import (
    create_auction_session,
    create_group,
    create_membership,
    list_groups,
)

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.get("", response_model=list[GroupResponse] | PaginatedResponse[GroupResponse])
async def list_groups_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_groups(db, current_user, page=page, page_size=pageSize)


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_group(db, payload, current_user)


@router.post(
    "/{group_id}/memberships",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership_endpoint(
    group_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_membership(db, group_id, payload, current_user)


@router.post(
    "/{group_id}/join",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_group_endpoint(
    group_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return join_group(db, group_id, payload, current_user)


@router.post(
    "/{group_id}/auction-sessions",
    response_model=AuctionSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_auction_session_endpoint(
    group_id: int,
    payload: AuctionSessionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_auction_session(db, group_id, payload, current_user)
