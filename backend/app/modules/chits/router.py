import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import APP_LOGGER_NAME
from app.core.rate_limiter import enforce_request_rate_limit
from app.core.security import CurrentUser, get_current_user, get_optional_current_user
from app.modules.chits.schemas import MembershipDecisionRequest, MembershipInviteRequest, MembershipRequestResponse
from app.modules.chits.service import (
    accept_membership_invite,
    approve_membership_request,
    invite_subscriber,
    list_chits_by_code,
    list_owner_membership_requests,
    list_public_chits,
    reject_membership_invite,
    reject_membership_request,
    request_membership,
)
from app.modules.groups.schemas import GroupResponse, MembershipResponse

router = APIRouter(prefix="/api/chits", tags=["chits"])
logger = logging.getLogger(APP_LOGGER_NAME)


@router.get("/public", response_model=list[GroupResponse])
async def list_public_chits_endpoint(db: Session = Depends(get_db)):
    return list_public_chits(db)


@router.get("/code/{group_code}", response_model=list[GroupResponse])
async def list_chits_by_code_endpoint(
    group_code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
):
    allowed, retry_after, identity = enforce_request_rate_limit(
        request,
        family="chits:code-search",
        limit=settings.chit_code_rate_limit_requests,
        window_seconds=settings.chit_code_rate_limit_window_seconds,
    )
    if not allowed:
        logger.warning(
            "Chit code search rate limit exceeded",
            extra={
                "event": "chit.code_search.rate_limited",
                "identity": identity,
                "group_code": group_code,
                "retry_after_seconds": retry_after,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    return list_chits_by_code(db, group_code, current_user)


@router.get("/owner/requests")
async def list_owner_membership_requests_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_membership_requests(db, current_user)


@router.post("/{group_id}/request", response_model=MembershipRequestResponse)
async def request_membership_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return request_membership(db, group_id, current_user)


@router.post("/{group_id}/invite", response_model=MembershipRequestResponse)
async def invite_subscriber_endpoint(
    group_id: int,
    payload: MembershipInviteRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return invite_subscriber(db, group_id, payload.phone, current_user)


@router.post("/{group_id}/approve-member", response_model=MembershipResponse)
async def approve_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return approve_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-member", response_model=MembershipRequestResponse)
async def reject_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/accept-invite", response_model=MembershipResponse)
async def accept_membership_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return accept_membership_invite(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-invite", response_model=MembershipRequestResponse)
async def reject_membership_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_membership_invite(db, group_id, payload.membershipId, current_user)
