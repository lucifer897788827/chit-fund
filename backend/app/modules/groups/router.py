from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.groups.schemas import (
    AuctionSessionCreate,
    AuctionSessionResponse,
    GroupCreate,
    GroupResponse,
    MembershipCreate,
    MembershipResponse,
)
from app.modules.groups.service import (
    create_auction_session,
    create_group,
    create_membership,
    list_groups,
)

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.get("", response_model=list[GroupResponse])
async def list_groups_endpoint(ownerId: int, db: Session = Depends(get_db)):
    return list_groups(db, ownerId)


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(payload: GroupCreate, db: Session = Depends(get_db)):
    return create_group(db, payload)


@router.post(
    "/{group_id}/memberships",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership_endpoint(
    group_id: int, payload: MembershipCreate, db: Session = Depends(get_db)
):
    return create_membership(db, group_id, payload)


@router.post(
    "/{group_id}/auction-sessions",
    response_model=AuctionSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_auction_session_endpoint(
    group_id: int, payload: AuctionSessionCreate, db: Session = Depends(get_db)
):
    return create_auction_session(db, group_id, payload)
