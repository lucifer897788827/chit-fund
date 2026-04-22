from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _build_engine(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_use_lifo=True,
    )


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_engine(database_url: str):
    global engine, SessionLocal
    engine = _build_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
