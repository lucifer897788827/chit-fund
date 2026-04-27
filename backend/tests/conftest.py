import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-suite-bootstrap.db")

from app.core import database
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.rate_limiter import rate_limiter
from app.core.security import hash_password
from app.main import app as fastapi_app
from app.models import Owner, Subscriber, User


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.db"
    database_url = f"sqlite:///{database_path}"
    settings.database_url = database_url
    previous_task_always_eager = celery_app.conf.task_always_eager
    previous_task_ignore_result = celery_app.conf.task_ignore_result
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_ignore_result = True
    database.init_engine(database_url)
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    rate_limiter.clear()

    with database.SessionLocal() as db:
        owner_user = User(
            email="owner@example.com",
            phone="9999999999",
            password_hash=hash_password("secret123"),
            role="chit_owner",
            is_active=True,
        )
        db.add(owner_user)
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

        owner_subscriber = Subscriber(
            user_id=owner_user.id,
            owner_id=owner.id,
            full_name="Owner One",
            phone=owner_user.phone,
            email=owner_user.email,
            status="active",
            auto_created=False,
        )
        db.add(owner_subscriber)
        db.flush()

        subscriber_user = User(
            email="subscriber@example.com",
            phone="8888888888",
            password_hash=hash_password("pass123"),
            role="subscriber",
            is_active=True,
        )
        db.add(subscriber_user)
        db.flush()
        subscriber = Subscriber(
            user_id=subscriber_user.id,
            owner_id=owner.id,
            full_name="Subscriber One",
            phone=subscriber_user.phone,
            email=subscriber_user.email,
            status="active",
            auto_created=False,
        )
        db.add(subscriber)
        db.commit()

    try:
        yield fastapi_app
    finally:
        rate_limiter.clear()
        celery_app.conf.task_always_eager = previous_task_always_eager
        celery_app.conf.task_ignore_result = previous_task_ignore_result


@pytest.fixture
def db_session():
    with database.SessionLocal() as db:
        yield db
