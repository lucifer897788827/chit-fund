from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, text
from sqlalchemy.orm import Session, configure_mappers

from app.core import database
from app.core.logging import APP_LOGGER_NAME
from app.core.money import money_int
from app.core.redis import redis_client
from app.core.security import CurrentUser, create_access_token
from app.core.time import utcnow
from app.models import AuctionBid, AuctionSession, Installment, Owner, Payout, Subscriber, User
from app.models.auction import AuctionResult
from app.models.chit import ChitGroup
from app.modules.auth.schemas import TokenResponse
from app.modules.auctions.schemas import AuctionFinalizeResponse
import app.core.security as security_module
import app.modules.auctions.service as auction_service

logger = logging.getLogger(APP_LOGGER_NAME)


def _warm_database_connection() -> dict[str, Any]:
    started_at = perf_counter()
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def _warm_redis_connection() -> dict[str, Any]:
    started_at = perf_counter()
    connected = redis_client.ping()
    return {
        "status": "ready" if connected else "unavailable",
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def _warm_finalize_models() -> dict[str, Any]:
    started_at = perf_counter()
    configure_mappers()
    for model in (AuctionSession, AuctionBid, Payout, Installment):
        _ = model.__table__
        _ = model.__mapper__
        _ = tuple(model.__mapper__.relationships)
    _ = tuple(database.Base.metadata.sorted_tables)
    return {
        "status": "ready",
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def _build_transient_finalized_session(
    session: AuctionSession,
    *,
    finalized_by_user_id: int,
    winning_bid_id: int | None,
    effective_now: datetime,
) -> AuctionSession:
    return AuctionSession(
        id=session.id,
        group_id=session.group_id,
        cycle_no=session.cycle_no,
        scheduled_start_at=session.scheduled_start_at,
        actual_start_at=session.actual_start_at,
        actual_end_at=session.actual_end_at or effective_now,
        start_time=session.start_time,
        end_time=session.end_time,
        auction_mode=session.auction_mode,
        commission_mode=session.commission_mode,
        commission_value=session.commission_value,
        min_bid_value=session.min_bid_value,
        max_bid_value=session.max_bid_value,
        min_increment=session.min_increment,
        bidding_window_seconds=session.bidding_window_seconds,
        status="finalized",
        opened_by_user_id=session.opened_by_user_id,
        closed_by_user_id=session.closed_by_user_id or finalized_by_user_id,
        winning_bid_id=winning_bid_id,
        created_at=session.created_at,
        updated_at=effective_now,
    )


def _build_transient_auction_result(
    session: AuctionSession,
    group: ChitGroup,
    *,
    winning_bid: AuctionBid,
    winner_membership_id: int,
    payout_snapshot: dict[str, int],
    finalized_by_user_id: int,
    effective_now: datetime,
) -> AuctionResult:
    return AuctionResult(
        id=0,
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=session.cycle_no,
        winner_membership_id=winner_membership_id,
        winning_bid_id=winning_bid.id,
        winning_bid_amount=money_int(winning_bid.bid_amount),
        dividend_pool_amount=int(payout_snapshot["dividendPoolAmount"]),
        dividend_per_member_amount=int(payout_snapshot["dividendPerMemberAmount"]),
        owner_commission_amount=int(payout_snapshot["ownerCommissionAmount"]),
        winner_payout_amount=int(payout_snapshot["winnerPayoutAmount"]),
        finalized_by_user_id=finalized_by_user_id,
        finalized_at=effective_now,
        created_at=effective_now,
    )


def _load_finalize_warmup_candidate(
    db: Session,
) -> tuple[AuctionSession, ChitGroup, Owner, User, Subscriber | None] | None:
    row = db.execute(
        select(AuctionSession, ChitGroup, Owner, User, Subscriber)
        .join(ChitGroup, ChitGroup.id == AuctionSession.group_id)
        .join(Owner, Owner.id == ChitGroup.owner_id)
        .join(User, User.id == Owner.user_id)
        .outerjoin(Subscriber, Subscriber.user_id == User.id)
        .where(AuctionSession.status.in_(("open", "closed", "finalizing", "finalized")))
        .order_by(AuctionSession.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    session, group, owner, owner_user, owner_subscriber = row
    return session, group, owner, owner_user, owner_subscriber


def warm_finalize_function_paths(db: Session) -> dict[str, Any]:
    started_at = perf_counter()

    # Warm startup-only imports that are normally loaded on the first finalize dispatch.
    auction_service._finalize_task_executes_inline()
    from app.tasks import auction_tasks as _auction_tasks  # noqa: F401

    candidate = _load_finalize_warmup_candidate(db)
    if candidate is None:
        return {
            "status": "skipped",
            "reason": "no_finalize_candidate",
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    session, _group, owner, owner_user, owner_subscriber = candidate
    current_user = CurrentUser(user=owner_user, owner=owner, subscriber=owner_subscriber)
    effective_now = utcnow()
    security_module._resolve_current_user(
        SimpleNamespace(state=SimpleNamespace()),
        HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token(str(owner_user.id)),
        ),
        db,
    )

    warmed_session, warmed_group = auction_service._get_owner_session(db, session.id, current_user)
    context = auction_service._load_finalize_enqueue_context(db, session_id=session.id, current_user=current_user)
    auction_service._can_enqueue_finalize_request_from_context(
        session=context.session,
        has_valid_bid=context.has_valid_bid,
        current_time=effective_now,
    )
    auction_service._build_enqueued_finalize_response(
        db,
        session=warmed_session,
        group=warmed_group,
        current_user=current_user,
    )

    total_bid_count, valid_bid_count = auction_service._get_bid_count_snapshot(db, warmed_session.id)
    existing_result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == warmed_session.id))
    if existing_result is not None:
        winner_details = auction_service._get_membership_display_details_joined(
            db,
            existing_result.winner_membership_id,
        )
        auction_service._build_finalization_response(
            db,
            session=warmed_session,
            group=warmed_group,
            result=existing_result,
            current_user=current_user,
            fallback_finalized_by_user_id=current_user.user.id,
            total_bids=total_bid_count,
            valid_bid_count=valid_bid_count,
            winner_details=winner_details,
            finalized_by_name=owner.display_name,
        )
    elif auction_service._can_enqueue_finalize_request(
        db,
        session=warmed_session,
        current_time=effective_now,
    ):
        winning_bid, winner_membership_id = auction_service._select_winning_bid_for_finalize(
            db,
            session=warmed_session,
            group=warmed_group,
            effective_now=effective_now,
        )
        if winning_bid is not None and winner_membership_id is not None:
            payout_snapshot = auction_service._build_minimal_payout_snapshot(
                session=warmed_session,
                group=warmed_group,
                winning_bid_amount=money_int(winning_bid.bid_amount),
            )
            winner_details = auction_service._get_membership_display_details_joined(db, winner_membership_id)
            finalized_session = _build_transient_finalized_session(
                warmed_session,
                finalized_by_user_id=current_user.user.id,
                winning_bid_id=winning_bid.id,
                effective_now=effective_now,
            )
            transient_result = _build_transient_auction_result(
                warmed_session,
                warmed_group,
                winning_bid=winning_bid,
                winner_membership_id=winner_membership_id,
                payout_snapshot=payout_snapshot,
                finalized_by_user_id=current_user.user.id,
                effective_now=effective_now,
            )
            auction_service._build_finalization_response(
                db,
                session=finalized_session,
                group=warmed_group,
                result=transient_result,
                current_user=current_user,
                fallback_finalized_by_user_id=current_user.user.id,
                total_bids=total_bid_count,
                valid_bid_count=valid_bid_count,
                winner_details=winner_details,
                finalized_by_name=owner.display_name,
            )

    db.rollback()
    return {
        "status": "ready",
        "session_id": int(session.id),
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def build_finalize_response_warmup_payload() -> dict[str, Any]:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return {
        "sessionId": 0,
        "groupId": 0,
        "auctionMode": "LIVE",
        "commissionMode": "NONE",
        "commissionValue": None,
        "cycleNo": 1,
        "status": "finalized",
        "closedAt": now,
        "finalizedAt": now,
        "closedByUserId": 1,
        "finalizedByUserId": 1,
        "finalizedByName": "Warmup Owner",
        "finalizationMessage": "Auction closed and finalized.",
        "resultSummary": {
            "sessionId": 0,
            "status": "finalized",
            "totalBids": 1,
            "validBidCount": 1,
            "auctionResultId": 0,
            "winnerMembershipId": 1,
            "winnerMembershipNo": 1,
            "winnerName": "Warmup Winner",
            "winningBidId": 1,
            "winningBidAmount": 10000,
            "ownerCommissionAmount": 0,
            "dividendPoolAmount": 0,
            "dividendPerMemberAmount": 0,
            "winnerPayoutAmount": 190000,
        },
        "console": {
            "sessionId": 0,
            "groupTitle": "Warmup Group",
            "groupCode": "WARMUP-000",
            "auctionMode": "LIVE",
            "commissionMode": "NONE",
            "commissionValue": None,
            "minBidValue": 0,
            "maxBidValue": 200000,
            "minIncrement": 1,
            "auctionState": "RESULT",
            "cycleNo": 1,
            "status": "finalized",
            "scheduledStartAt": now,
            "actualStartAt": now,
            "actualEndAt": now,
            "startTime": now,
            "endTime": now,
            "serverTime": now,
            "totalBidCount": 1,
            "validBidCount": 1,
            "highestBidAmount": 10000,
            "highestBidMembershipNo": 1,
            "highestBidderName": "Warmup Winner",
            "canFinalize": False,
            "auctionResultId": 0,
            "finalizedAt": now,
            "finalizedByName": "Warmup Owner",
            "winnerMembershipId": 1,
            "winnerMembershipNo": 1,
            "winnerName": "Warmup Winner",
            "winningBidId": 1,
            "winningBidAmount": 10000,
            "ownerCommissionAmount": 0,
            "dividendPoolAmount": 0,
            "dividendPerMemberAmount": 0,
            "winnerPayoutAmount": 190000,
            "finalizationMessage": "Auction closed and finalized.",
        },
    }


def warm_finalize_response_path() -> dict[str, Any]:
    started_at = perf_counter()
    payload = build_finalize_response_warmup_payload()
    validated = AuctionFinalizeResponse.model_validate(payload)
    jsonable_encoder(validated)
    validated.model_dump(mode="json")
    return {
        "status": "ready",
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def warm_auth_response_path() -> dict[str, Any]:
    started_at = perf_counter()
    payload = {
        "access_token": create_access_token("0"),
        "token_type": "bearer",
        "refresh_token": "warmup-refresh-token",
        "refresh_token_expires_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "access_token_expires_in": 900,
        "refresh_token_expires_in": 2592000,
        "role": "subscriber",
        "roles": ["subscriber"],
        "owner_id": None,
        "subscriber_id": 1,
        "has_subscriber_profile": True,
        "user": {"id": 0, "roles": ["subscriber"]},
    }
    validated = TokenResponse.model_validate(payload)
    jsonable_encoder(validated)
    validated.model_dump(mode="json")
    return {
        "status": "ready",
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }


def run_startup_warmup() -> dict[str, Any]:
    started_at = perf_counter()
    results: dict[str, Any] = {}

    try:
        results["db"] = _warm_database_connection()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup DB warmup failed",
            extra={"event": "app.startup.warmup.db_failed"},
        )
        results["db"] = {"status": "failed", "error": str(exc)}

    try:
        results["redis"] = _warm_redis_connection()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup Redis warmup failed",
            extra={"event": "app.startup.warmup.redis_failed"},
        )
        results["redis"] = {"status": "failed", "error": str(exc)}

    try:
        results["orm"] = _warm_finalize_models()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup ORM warmup failed",
            extra={"event": "app.startup.warmup.orm_failed"},
        )
        results["orm"] = {"status": "failed", "error": str(exc)}

    try:
        with database.SessionLocal() as db:
            results["finalize"] = warm_finalize_function_paths(db)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup finalize warmup failed",
            extra={"event": "app.startup.warmup.finalize_failed"},
        )
        results["finalize"] = {"status": "failed", "error": str(exc)}

    try:
        results["response"] = warm_finalize_response_path()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup finalize response warmup failed",
            extra={"event": "app.startup.warmup.response_failed"},
        )
        results["response"] = {"status": "failed", "error": str(exc)}

    try:
        results["auth_response"] = warm_auth_response_path()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Startup auth response warmup failed",
            extra={"event": "app.startup.warmup.auth_response_failed"},
        )
        results["auth_response"] = {"status": "failed", "error": str(exc)}

    logger.info(
        "Startup warmup completed",
        extra={
            "event": "app.startup.warmup.completed",
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            "db_status": results.get("db", {}).get("status"),
            "redis_status": results.get("redis", {}).get("status"),
            "orm_status": results.get("orm", {}).get("status"),
            "finalize_status": results.get("finalize", {}).get("status"),
            "response_status": results.get("response", {}).get("status"),
            "auth_response_status": results.get("auth_response", {}).get("status"),
        },
    )
    return results
