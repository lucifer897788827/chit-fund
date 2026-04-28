import logging
from functools import wraps

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
LEGACY_SUNSET = "Wed, 30 Sep 2026 23:59:59 GMT"


def _log_legacy_route_usage(path: str, current_user: CurrentUser | None = None) -> None:
    logger.warning(
        "Legacy chit membership API used",
        extra={
            "event": "api.deprecation.legacy_chits_route_used",
            "legacy_path": path,
            "user_id": getattr(getattr(current_user, "user", None), "id", None),
        },
    )


def _legacy_headers() -> dict[str, str]:
    return {
        "Deprecation": "true",
        "Sunset": LEGACY_SUNSET,
        "Link": '</api/groups>; rel="successor-version"',
        "Warning": '299 - "Deprecated API, use /api/groups endpoints instead."',
    }


def _apply_legacy_headers(response: Response) -> None:
    for key, value in _legacy_headers().items():
        response.headers[key] = value


def _legacy_route(handler):
    @wraps(handler)
    async def wrapped(*args, **kwargs):
        response = kwargs.get("response")
        if isinstance(response, Response):
            _apply_legacy_headers(response)
        try:
            return await handler(*args, **kwargs)
        except HTTPException as exc:
            headers = dict(exc.headers or {})
            headers.update(_legacy_headers())
            raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=headers) from exc

    return wrapped


@router.get("/public", response_model=list[GroupResponse])
@_legacy_route
async def list_public_chits_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return list_public_chits(db)


@router.get("/code/{group_code}", response_model=list[GroupResponse])
@_legacy_route
async def list_chits_by_code_endpoint(
    group_code: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
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
@_legacy_route
async def list_owner_membership_requests_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return list_owner_membership_requests(db, current_user)


@router.post("/{group_id}/request", response_model=MembershipRequestResponse)
@_legacy_route
async def request_membership_endpoint(
    group_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return request_membership(db, group_id, current_user)


@router.post("/{group_id}/invite", response_model=MembershipRequestResponse)
@_legacy_route
async def invite_subscriber_endpoint(
    group_id: int,
    payload: MembershipInviteRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return invite_subscriber(db, group_id, payload.phone, current_user)


@router.post("/{group_id}/approve-member", response_model=MembershipResponse)
@_legacy_route
async def approve_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return approve_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-member", response_model=MembershipRequestResponse)
@_legacy_route
async def reject_membership_request_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return reject_membership_request(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/accept-invite", response_model=MembershipResponse)
@_legacy_route
async def accept_membership_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return accept_membership_invite(db, group_id, payload.membershipId, current_user)


@router.post("/{group_id}/reject-invite", response_model=MembershipRequestResponse)
@_legacy_route
async def reject_membership_invite_endpoint(
    group_id: int,
    payload: MembershipDecisionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _log_legacy_route_usage(request.url.path, current_user)
    return reject_membership_invite(db, group_id, payload.membershipId, current_user)
