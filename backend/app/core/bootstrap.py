from datetime import date, datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app.core import config as config_module
from app.core import database
from app.core.logging import APP_LOGGER_NAME
from app.core.security import hash_password
from app.models import AuctionSession, ChitGroup, ExternalChit, GroupMembership, Installment, MembershipSlot, Owner, Subscriber, User

logger = logging.getLogger(APP_LOGGER_NAME)


def _schema_exists_without_alembic_version() -> bool:
    with database.SessionLocal() as db:
        table_names = set(inspect(db.connection()).get_table_names())

    if "alembic_version" in table_names:
        return False

    managed_tables = set(database.Base.metadata.tables.keys())
    return any(table_name in table_names for table_name in managed_tables)


def _run_migrations() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))

    if _schema_exists_without_alembic_version():
        command.stamp(alembic_cfg, "head")

    command.upgrade(alembic_cfg, "head")


def bootstrap_database() -> None:
    _run_migrations()

    if not config_module.settings.is_dev_profile:
        return

    with database.SessionLocal() as db:
        existing_user = db.scalar(select(User.id).limit(1))
        if existing_user is not None:
            return

        owner_user = User(
            email="owner@example.com",
            phone="9999999999",
            password_hash=hash_password("secret123"),
            role="chit_owner",
            is_active=True,
        )
        subscriber_user = User(
            email="subscriber@example.com",
            phone="8888888888",
            password_hash=hash_password("pass123"),
            role="subscriber",
            is_active=True,
        )
        db.add_all([owner_user, subscriber_user])
        db.flush()

        owner = Owner(
            user_id=owner_user.id,
            display_name="Owner One",
            business_name="Owner One Chits",
            city="Chennai",
            state="Tamil Nadu",
            status="active",
        )
        db.add(owner)
        db.flush()

        owner_profile = Subscriber(
            user_id=owner_user.id,
            owner_id=owner.id,
            full_name="Owner One",
            phone=owner_user.phone,
            email=owner_user.email,
            status="active",
            auto_created=False,
        )
        subscriber_profile = Subscriber(
            user_id=subscriber_user.id,
            owner_id=owner.id,
            full_name="Subscriber One",
            phone=subscriber_user.phone,
            email=subscriber_user.email,
            status="active",
            auto_created=False,
        )
        db.add_all([owner_profile, subscriber_profile])
        db.flush()

        group = ChitGroup(
            owner_id=owner.id,
            group_code="CHIT-001",
            title="April Gold Circle",
            chit_value=300000,
            installment_amount=15000,
            member_count=20,
            cycle_count=20,
            cycle_frequency="monthly",
            start_date=date(2026, 4, 1),
            first_auction_date=date(2026, 4, 20),
            current_cycle_no=1,
            bidding_enabled=True,
            status="active",
        )
        db.add(group)
        db.flush()

        memberships = [
            GroupMembership(
                group_id=group.id,
                subscriber_id=owner_profile.id,
                member_no=1,
                membership_status="active",
                prized_status="unprized",
                can_bid=True,
            ),
            GroupMembership(
                group_id=group.id,
                subscriber_id=subscriber_profile.id,
                member_no=2,
                membership_status="active",
                prized_status="unprized",
                can_bid=True,
            ),
        ]
        db.add_all(memberships)
        db.flush()

        db.add_all(
            [
                MembershipSlot(
                    user_id=owner_user.id,
                    group_id=group.id,
                    slot_number=memberships[0].member_no,
                    has_won=False,
                ),
                MembershipSlot(
                    user_id=subscriber_user.id,
                    group_id=group.id,
                    slot_number=memberships[1].member_no,
                    has_won=False,
                ),
            ]
        )

        for membership in memberships:
            db.add(
                Installment(
                    group_id=group.id,
                    membership_id=membership.id,
                    cycle_no=1,
                    due_date=group.start_date,
                    due_amount=group.installment_amount,
                    penalty_amount=0,
                    paid_amount=0,
                    balance_amount=group.installment_amount,
                    status="pending",
                )
            )

        db.add(
            AuctionSession(
                group_id=group.id,
                cycle_no=1,
                scheduled_start_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                actual_start_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                bidding_window_seconds=180,
                status="open",
                opened_by_user_id=owner_user.id,
            )
        )
        db.add(
            ExternalChit(
                subscriber_id=subscriber_profile.id,
                title="Neighbourhood Savings Pot",
                organizer_name="Lakshmi",
                chit_value=120000,
                installment_amount=6000,
                cycle_frequency="monthly",
                start_date=date(2026, 3, 1),
                status="active",
            )
        )
        db.commit()


def check_database_readiness() -> dict[str, Any]:
    try:
        with database.SessionLocal() as db:
            db.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover - exercised through health tests
        return {
            "ok": False,
            "status": "down",
            "detail": str(exc),
        }

    return {
        "ok": True,
        "status": "up",
    }


def check_redis_readiness() -> dict[str, Any]:
    from app.core.redis import redis_client

    try:
        ok = redis_client.ping()
    except Exception as exc:  # pragma: no cover - defensive fallback
        return {
            "ok": False,
            "status": "down",
            "detail": str(exc),
        }

    if not ok:
        return {
            "ok": False,
            "status": "down",
            "detail": "ping failed",
        }

    return {
        "ok": True,
        "status": "up",
    }


def check_celery_broker_readiness() -> dict[str, Any]:
    from app.core.celery_app import celery_app

    connection = celery_app.connection_for_read()
    try:
        connection.ensure_connection(
            max_retries=1,
            interval_start=0,
            interval_step=0,
            interval_max=0,
        )
    except Exception as exc:  # pragma: no cover - exercised through health tests
        return {
            "ok": False,
            "status": "down",
            "detail": str(exc),
        }
    finally:
        try:
            connection.release()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass

    return {
        "ok": True,
        "status": "up",
    }


def check_configuration_readiness() -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []

    database_url = str(config_module.settings.database_url or "")
    jwt_secret = str(config_module.settings.jwt_secret or "")
    cors_origins = [str(origin).strip() for origin in config_module.settings.cors_origins]
    frontend_backend_url = str(os.getenv("REACT_APP_BACKEND_URL") or "").strip()

    if config_module.settings.is_production_profile:
        localhost_origins = [origin for origin in cors_origins if "localhost" in origin or "127.0.0.1" in origin]
        wildcard_origins = [origin for origin in cors_origins if origin == "*"]
        if not cors_origins:
            issues.append("CORS_ORIGINS is empty")
        if localhost_origins:
            issues.append("CORS_ORIGINS contains localhost entries")
        if wildcard_origins:
            issues.append("CORS_ORIGINS contains wildcard entries")
        if database_url.startswith("sqlite"):
            issues.append("DATABASE_URL points to sqlite")
        if "localhost" in database_url or "127.0.0.1" in database_url:
            warnings.append("DATABASE_URL references localhost")
        if len(jwt_secret) < 32 or jwt_secret.lower() in {"test", "test-secret", "secret", "changeme"}:
            issues.append("JWT_SECRET is weak")
        if frontend_backend_url:
            if "localhost" in frontend_backend_url or "127.0.0.1" in frontend_backend_url:
                issues.append("REACT_APP_BACKEND_URL points to localhost")
        else:
            warnings.append("REACT_APP_BACKEND_URL is not set")

    status = "up" if not issues else "misconfigured"
    payload: dict[str, Any] = {
        "ok": not issues,
        "status": status,
    }
    if issues:
        payload["issues"] = issues
    if warnings:
        payload["warnings"] = warnings
    return payload


def assert_startup_configuration_safe() -> None:
    if not config_module.settings.is_production_profile:
        return

    configuration = check_configuration_readiness()
    issues = configuration.get("issues") or []
    if not issues:
        return

    issue_text = "; ".join(str(issue) for issue in issues)
    logger.error(
        "app.startup.configuration_invalid",
        extra={
            "event": "app.startup.configuration_invalid",
            "issues": issues,
        },
    )
    raise RuntimeError(f"Unsafe production configuration: {issue_text}")


def check_finalize_worker_readiness() -> dict[str, Any]:
    from app.tasks.auction_tasks import get_finalize_job_worker_health

    worker_health = get_finalize_job_worker_health()
    status = str(worker_health.get("status") or "unknown")
    ok = status in {"ready", "idle", "degraded"}
    return {
        "ok": ok,
        "status": status,
        **worker_health,
    }


def build_runtime_readiness_report() -> dict[str, Any]:
    checks = {
        "database": check_database_readiness(),
        "redis": check_redis_readiness(),
        "celeryBroker": check_celery_broker_readiness(),
        "configuration": check_configuration_readiness(),
        "worker": check_finalize_worker_readiness(),
    }
    ready = bool(checks["database"]["ok"] and checks["configuration"]["ok"])
    status = "ok" if ready and all(check["ok"] for check in checks.values()) else "degraded"

    return {
        "status": status,
        "ready": ready,
        "environment": config_module.settings.app_env,
        "checks": checks,
    }
