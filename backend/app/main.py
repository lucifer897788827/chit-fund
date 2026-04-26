import asyncio
from contextlib import asynccontextmanager, suppress
from time import perf_counter
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import database
from app.core.bootstrap import assert_startup_configuration_safe, bootstrap_database, build_runtime_readiness_report
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limiter import RateLimitMiddleware
from app.core.startup_warmup import run_startup_warmup
from app.core.websocket import connection_manager
from app.modules.admin.router import router as admin_router
from app.modules.auctions.router import router as auctions_router
from app.modules.auctions.realtime_router import router as auctions_realtime_router
from app.modules.auctions.realtime_service import (
    INSTANCE_ID as AUCTION_REALTIME_INSTANCE_ID,
    close_auction_event_listener,
    read_next_auction_event,
    subscribe_to_all_auction_events,
)
from app.modules.auth.router import router as auth_router
from app.modules.chits.router import router as chits_router
from app.modules.external_chits.router import router as external_chits_router
from app.modules.groups.router import router as groups_router
from app.modules.job_tracking.router import router as job_tracking_router
from app.modules.notifications.router import router as notifications_router
from app.modules.owner_requests.router import router as owner_requests_router
from app.modules.payments.payout_router import router as payout_router
from app.modules.payments.router import router as payments_router
from app.modules.reporting.router import router as reporting_router
from app.modules.subscribers.router import router as subscribers_router
from app.modules.support.router import router as support_router
from app.modules.users.router import router as users_router


app_logger = configure_logging(
    app_env=settings.app_env,
    structured_logging=settings.structured_logging,
    level=settings.log_level,
)
_REQUEST_METRICS_LOCK = Lock()
_REQUEST_METRICS = {
    "requests_total": 0,
    "errors_total": 0,
    "duration_ms_total": 0.0,
}


def _first_error_message(detail: Any, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, list):
        for item in detail:
            if isinstance(item, dict):
                message = item.get("msg")
                if isinstance(message, str) and message.strip():
                    return message
            if isinstance(item, str) and item.strip():
                return item
    if isinstance(detail, dict):
        for key in ("error", "message", "detail"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return fallback


def _build_error_response(
    *,
    status_code: int,
    error_message: str,
    detail: Any,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = {
        "success": False,
        "error": error_message,
        "detail": detail,
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        status_code=status_code,
        headers=headers,
    )


async def _relay_auction_realtime_events(stop_event: asyncio.Event):
    pubsub = subscribe_to_all_auction_events()
    if pubsub is None:
        return

    try:
        while not stop_event.is_set():
            event = await asyncio.to_thread(read_next_auction_event, pubsub, 1.0)
            if event is None:
                continue

            if event.get("sourceInstanceId") == AUCTION_REALTIME_INSTANCE_ID:
                continue

            session_id = event.get("sessionId")
            if not isinstance(session_id, int):
                continue

            await connection_manager.broadcast(session_id, event)
    finally:
        await asyncio.to_thread(close_auction_event_listener, pubsub)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    assert_startup_configuration_safe()
    bootstrap_database()
    run_startup_warmup()
    stop_event = asyncio.Event()
    realtime_task = asyncio.create_task(_relay_auction_realtime_events(stop_event))
    app_logger.info(
        "app.startup",
        extra={
            "event": "app.startup",
            "app_env": settings.app_env,
            "app_name": settings.app_name,
        },
    )
    try:
        yield
    finally:
        stop_event.set()
        realtime_task.cancel()
        with suppress(asyncio.CancelledError):
            await realtime_task


def apply_global_cors(asgi_app: Any) -> CORSMiddleware:
    # Wrap the full ASGI stack so preflight and top-level error responses both keep CORS headers.
    return CORSMiddleware(
        app=asgi_app,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, lifespan=lifespan)

    application.add_middleware(RateLimitMiddleware)

    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(chits_router)
    application.include_router(subscribers_router)
    application.include_router(support_router)
    application.include_router(groups_router)
    application.include_router(owner_requests_router)
    application.include_router(job_tracking_router)
    application.include_router(notifications_router)
    application.include_router(auctions_router)
    application.include_router(auctions_realtime_router)
    application.include_router(payout_router)
    application.include_router(payments_router)
    application.include_router(reporting_router)
    application.include_router(external_chits_router)
    application.include_router(users_router)

    @application.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        return _build_error_response(
            status_code=exc.status_code,
            error_message=_first_error_message(exc.detail, "Request failed."),
            detail=exc.detail,
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(_request: Request, exc: RequestValidationError):
        detail = exc.errors()
        return _build_error_response(
            status_code=422,
            error_message=_first_error_message(detail, "Request validation failed."),
            detail=detail,
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        app_logger.exception(
            "http.request.unhandled_exception",
            extra={
                "event": "http.request.unhandled_exception",
            },
        )
        detail = str(exc) if settings.is_dev_profile else "Internal server error"
        return _build_error_response(
            status_code=500,
            error_message="Internal server error",
            detail=detail,
        )

    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        started_at = perf_counter()
        with _REQUEST_METRICS_LOCK:
            _REQUEST_METRICS["requests_total"] += 1
        request_context = {
            "event": "http.request.started",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "app_env": settings.app_env,
        }
        app_logger.info("http.request.started", extra=request_context)

        try:
            response = await call_next(request)
        except Exception:
            with _REQUEST_METRICS_LOCK:
                _REQUEST_METRICS["errors_total"] += 1
            app_logger.exception(
                "http.request.failed",
                extra={
                    "event": "http.request.failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "app_env": settings.app_env,
                },
            )
            raise

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        with _REQUEST_METRICS_LOCK:
            _REQUEST_METRICS["duration_ms_total"] += duration_ms
            if response.status_code >= 500:
                _REQUEST_METRICS["errors_total"] += 1
        app_logger.info(
            "http.request.completed",
            extra={
                "event": "http.request.completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "app_env": settings.app_env,
            },
        )
        return response

    @application.get("/api/health")
    async def health():
        return {"status": "ok"}

    @application.get("/api/health/readiness")
    async def readiness():
        report = build_runtime_readiness_report()
        # Local development should stay probe-friendly even when dependencies are offline.
        status_code = 200 if report["ready"] or not settings.is_production_profile else 503
        return JSONResponse(content=report, status_code=status_code)

    @application.get("/api/readiness")
    async def readiness_alias():
        return await readiness()

    @application.get("/api/metrics")
    async def metrics():
        with _REQUEST_METRICS_LOCK:
            request_count = int(_REQUEST_METRICS["requests_total"])
            error_count = int(_REQUEST_METRICS["errors_total"])
            duration_ms_total = float(_REQUEST_METRICS["duration_ms_total"])
        average_duration_ms = round(duration_ms_total / request_count, 2) if request_count else 0.0
        error_rate = round(error_count / request_count, 4) if request_count else 0.0
        return {
            "requestsTotal": request_count,
            "errorsTotal": error_count,
            "errorRate": error_rate,
            "averageDurationMs": average_duration_ms,
        }

    @application.get("/api/db-test")
    async def db_test():
        try:
            with database.SessionLocal() as db:
                db.execute(text("select 1"))
        except Exception as exc:  # pragma: no cover - exercised in integration only
            app_logger.exception(
                "db.test.failed",
                extra={
                    "event": "db.test.failed",
                },
            )
            payload = {
                "success": False,
                "error": "Database is unreachable",
                "status": "error",
                "database": "unreachable",
            }
            if not settings.is_production_profile:
                payload["detail"] = str(exc)
            return JSONResponse(content=payload, status_code=503)

        return {"status": "ok", "database": "connected"}

    return application


fastapi_app = create_app()
app = apply_global_cors(fastapi_app)
