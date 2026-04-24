from sqlalchemy import inspect, select, text

from app.core import config as config_module
from app.core import database
from app.core.bootstrap import bootstrap_database
from app.models import User


def test_bootstrap_database_uses_alembic_and_preserves_dev_seeding(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'bootstrap.db'}"
    database.init_engine(database_url)

    monkeypatch.setattr(config_module.settings, "database_url", database_url)
    monkeypatch.setattr(config_module.settings, "app_env", "development")

    def fail_create_all(*args, **kwargs):
        raise AssertionError("bootstrap_database should use Alembic migrations instead of create_all")

    monkeypatch.setattr(type(database.Base.metadata), "create_all", fail_create_all)

    bootstrap_database()

    with database.SessionLocal() as db:
        user_ids = db.scalars(select(User.id).order_by(User.id)).all()

    assert user_ids == [1, 2]


def test_bootstrap_database_stamps_existing_schema_before_upgrade(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'precreated-schema.db'}"
    database.init_engine(database_url)

    monkeypatch.setattr(config_module.settings, "database_url", database_url)
    monkeypatch.setattr(config_module.settings, "app_env", "production")

    database.Base.metadata.create_all(bind=database.engine)

    bootstrap_database()

    with database.engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one()

    assert "users" in tables
    assert "alembic_version" in tables
    assert "membership_slots" in tables
    assert "finalize_jobs" in tables
    assert revision == "20260423_0021"
