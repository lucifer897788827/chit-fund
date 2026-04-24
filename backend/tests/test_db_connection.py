from app.core import database
from app.core.config import settings
from fastapi.testclient import TestClient


def test_db_test_endpoint_reports_connected_database(app):
    client = TestClient(app)

    response = client.get("/api/db-test")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
    }


def test_db_test_endpoint_returns_503_when_database_is_unreachable(app, monkeypatch):
    class _BrokenConnection:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, exc_type, exc, tb):
            return False

    class _BrokenEngine:
        def connect(self):
            return _BrokenConnection()

    monkeypatch.setattr(database, "engine", _BrokenEngine())
    client = TestClient(app)

    response = client.get("/api/db-test")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["database"] == "unreachable"


def test_database_engine_uses_profile_pool_settings(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    monkeypatch.setattr(settings, "database_pool_size", 3)
    monkeypatch.setattr(settings, "database_max_overflow", 1)
    monkeypatch.setattr(settings, "database_pool_timeout_seconds", 11)
    monkeypatch.setattr(settings, "database_pool_recycle_seconds", 22)

    engine = database._build_engine("postgresql://example/db")

    assert engine is not None
    assert captured["url"] == "postgresql://example/db"
    assert captured["kwargs"]["pool_size"] == 3
    assert captured["kwargs"]["max_overflow"] == 1
    assert captured["kwargs"]["pool_timeout"] == 11
    assert captured["kwargs"]["pool_recycle"] == 22
    assert captured["kwargs"]["pool_use_lifo"] is True


def test_non_sqlite_database_engine_enables_production_pooling(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    monkeypatch.setattr(database.settings, "database_pool_size", 8, raising=False)
    monkeypatch.setattr(database.settings, "database_max_overflow", 16, raising=False)
    monkeypatch.setattr(database.settings, "database_pool_timeout_seconds", 45, raising=False)
    monkeypatch.setattr(database.settings, "database_pool_recycle_seconds", 1200, raising=False)

    engine = database._build_engine("postgresql+psycopg://db.example.com/chits")

    assert engine is not None
    assert captured["url"] == "postgresql+psycopg://db.example.com/chits"
    assert captured["kwargs"]["pool_pre_ping"] is True
    assert captured["kwargs"]["pool_size"] == 8
    assert captured["kwargs"]["max_overflow"] == 16
    assert captured["kwargs"]["pool_timeout"] == 45
    assert captured["kwargs"]["pool_recycle"] == 1200
    assert captured["kwargs"]["pool_use_lifo"] is True
