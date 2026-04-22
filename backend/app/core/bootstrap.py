from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app.core import config as config_module
from app.core import database
from app.core.security import hash_password
from app.models import AuctionSession, ChitGroup, ExternalChit, GroupMembership, Installment, MembershipSlot, Owner, Subscriber, User


def _schema_exists_without_alembic_version() -> bool:
    with database.engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())

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
        )
        subscriber_profile = Subscriber(
            user_id=subscriber_user.id,
            owner_id=owner.id,
            full_name="Subscriber One",
            phone=subscriber_user.phone,
            email=subscriber_user.email,
            status="active",
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
        with database.engine.connect() as connection:
            connection.execute(text("select 1"))
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


def build_runtime_readiness_report() -> dict[str, Any]:
    checks = {
        "database": check_database_readiness(),
        "redis": check_redis_readiness(),
        "celeryBroker": check_celery_broker_readiness(),
    }
    ready = all(check["ok"] for check in checks.values())

    return {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "environment": config_module.settings.app_env,
        "checks": checks,
    }
