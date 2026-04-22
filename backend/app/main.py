import asyncio
from contextlib import asynccontextmanager, suppress
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import database
from app.core.bootstrap import bootstrap_database, build_runtime_readiness_report
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limiter import RateLimitMiddleware
from app.core.websocket import connection_manager
from app.modules.auctions.router import router as auctions_router
from app.modules.auctions.realtime_router import router as auctions_realtime_router
from app.modules.auctions.realtime_service import (
    INSTANCE_ID as AUCTION_REALTIME_INSTANCE_ID,
    close_auction_event_listener,
    read_next_auction_event,
    subscribe_to_all_auction_events,
)
from app.modules.auth.router import router as auth_router
from app.modules.external_chits.router import router as external_chits_router
from app.modules.groups.router import router as groups_router
from app.modules.job_tracking.router import router as job_tracking_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.router import router as payments_router
from app.modules.reporting.router import router as reporting_router
from app.modules.subscribers.router import router as subscribers_router
from app.modules.support.router import router as support_router


app_logger = configure_logging(
    app_env=settings.app_env,
    structured_logging=settings.structured_logging,
    level=settings.log_level,
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
    bootstrap_database()
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
    application.include_router(subscribers_router)
    application.include_router(support_router)
    application.include_router(groups_router)
    application.include_router(job_tracking_router)
    application.include_router(notifications_router)
    application.include_router(auctions_router)
    application.include_router(auctions_realtime_router)
    application.include_router(payments_router)
    application.include_router(reporting_router)
    application.include_router(external_chits_router)

    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        started_at = perf_counter()
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

    @application.get("/api/db-test")
    async def db_test():
        try:
            with database.engine.connect() as connection:
                connection.execute(text("select 1"))
        except Exception as exc:  # pragma: no cover - exercised in integration only
            return {"status": "error", "database": "unreachable", "detail": str(exc)}

        return {"status": "ok", "database": "connected"}

    return application


fastapi_app = create_app()
app = apply_global_cors(fastapi_app)
