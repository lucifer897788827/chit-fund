import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import APP_LOGGER_NAME
from app.core.pagination import PaginatedResponse
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
from app.modules.groups.schemas import (
    AuctionSessionCreate,
    AuctionSessionResponse,
    GroupCreate,
    GroupInviteAuditResponse,
    GroupInviteCandidateResponse,
    GroupInviteCreate,
    GroupInviteResponse,
    GroupMemberSummaryResponse,
    GroupMemberRemovalResponse,
    GroupSettingsUpdate,
    JoinRequestApprovalRequest,
    JoinRequestCreate,
    JoinRequestResponse,
    GroupResponse,
    GroupStatusResponse,
    MembershipCreate,
    MembershipResponse,
)
from app.modules.groups.invite_service import (
    create_group_invite,
    list_group_invites,
    revoke_group_invite,
    search_group_invite_candidates,
)
from app.modules.groups.join_request_service import approve_join_request, create_join_request, list_join_requests, reject_join_request
from app.modules.groups.join_service import join_group
from app.modules.groups.service import (
    close_group_collection,
    create_auction_session,
    create_group,
    create_membership,
    get_group_member_summary,
    get_group_status,
    list_groups,
    remove_group_member,
    update_group_settings,
)

router = APIRouter(prefix="/api/groups", tags=["groups"])
logger = logging.getLogger(APP_LOGGER_NAME)


@router.get("", response_model=list[GroupResponse] | PaginatedResponse[GroupResponse])
async def list_groups_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_groups(db, current_user, page=page, page_size=pageSize)


@router.get("/public", response_model=list[GroupResponse])
async def list_public_groups_endpoint(
    db: Session = Depends(get_db),
):
    return list_public_chits(db)


@router.get("/code/{group_code}", response_model=list[GroupResponse])
async def list_groups_by_code_endpoint(
    group_code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
):
    allowed, retry_after, identity = enforce_request_rate_limit(
        request,
        family="groups:code-search",
        limit=settings.chit_code_rate_limit_requests,
        window_seconds=settings.chit_code_rate_limit_window_seconds,
    )
    if not allowed:
        logger.warning(
            "Group code search rate limit exceeded",
            extra={
                "event": "group.code_search.rate_limited",
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


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_group(db, payload, current_user)


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group_settings_endpoint(
    group_id: int,
    payload: GroupSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return update_group_settings(db, group_id, payload, current_user)


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


@router.post("/{group_id}/close-collection", response_model=GroupResponse)
async def close_group_collection_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return close_group_collection(db, group_id, current_user)


@router.get("/{group_id}/status", response_model=GroupStatusResponse)
async def get_group_status_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_group_status(db, group_id, current_user)


@router.get("/{group_id}/member-summary", response_model=list[GroupMemberSummaryResponse])
async def get_group_member_summary_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_group_member_summary(db, group_id, current_user)


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
    "/{group_id}/request",
    response_model=MembershipRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_group_membership_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return request_membership(db, group_id, current_user)


@router.post(
    "/{group_id}/join-request",
    response_model=JoinRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_join_request_endpoint(
    group_id: int,
    payload: JoinRequestCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_join_request(db, group_id, payload, current_user)


@router.get("/{group_id}/join-requests", response_model=list[JoinRequestResponse])
async def list_join_requests_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_join_requests(db, group_id, current_user)


@router.post("/{group_id}/approve-member", response_model=MembershipResponse)
async def approve_join_request_endpoint(
    group_id: int,
    payload: JoinRequestApprovalRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return approve_join_request(db, group_id, payload.joinRequestId, current_user)


@router.post("/{group_id}/reject-member", response_model=JoinRequestResponse)
async def reject_join_request_endpoint(
    group_id: int,
    payload: JoinRequestApprovalRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_join_request(db, group_id, payload.joinRequestId, current_user)


@router.post("/{group_id}/approve-membership-request", response_model=MembershipResponse)
async def approve_legacy_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return approve_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-membership-request", response_model=MembershipRequestResponse)
async def reject_legacy_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/memberships/{membership_id}/remove", response_model=GroupMemberRemovalResponse)
async def remove_group_member_endpoint(
    group_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return remove_group_member(db, group_id, membership_id, current_user)


@router.get("/{group_id}/search-users", response_model=list[GroupInviteCandidateResponse])
async def search_group_invite_candidates_endpoint(
    group_id: int,
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return search_group_invite_candidates(db, group_id, q, current_user)


@router.post("/{group_id}/invite", response_model=GroupInviteResponse)
async def create_group_invite_endpoint(
    group_id: int,
    payload: GroupInviteCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_group_invite(db, group_id, payload.subscriberId, current_user)


@router.get("/{group_id}/invites", response_model=list[GroupInviteAuditResponse])
async def list_group_invites_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_group_invites(db, group_id, current_user)


@router.post("/{group_id}/invites/{invite_id}/revoke", response_model=GroupInviteAuditResponse)
async def revoke_group_invite_endpoint(
    group_id: int,
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return revoke_group_invite(db, group_id, invite_id, current_user)


@router.post("/{group_id}/invite-by-phone", response_model=MembershipRequestResponse)
async def invite_subscriber_by_phone_endpoint(
    group_id: int,
    payload: MembershipInviteRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return invite_subscriber(db, group_id, payload.phone, current_user)


@router.post("/{group_id}/accept-invite", response_model=MembershipResponse)
async def accept_group_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return accept_membership_invite(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-invite", response_model=MembershipRequestResponse)
async def reject_group_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return reject_membership_invite(db, group_id, payload.membershipId, current_user)


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
