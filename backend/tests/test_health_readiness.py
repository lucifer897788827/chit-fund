from fastapi.testclient import TestClient
import app.core.bootstrap as bootstrap_module


def test_health_endpoint_remains_unchanged(app):
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_build_runtime_readiness_report_aggregates_dependency_checks(monkeypatch):
    monkeypatch.setattr(bootstrap_module.config_module.settings, "app_env", "production")
    monkeypatch.setattr(
        bootstrap_module,
        "check_database_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_redis_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_celery_broker_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_configuration_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_finalize_worker_readiness",
        lambda: {"ok": True, "status": "ready"},
    )

    report = bootstrap_module.build_runtime_readiness_report()

    assert report["status"] == "ok"
    assert report["ready"] is True
    assert report["environment"] == "production"
    assert report["checks"]["database"]["status"] == "up"
    assert report["checks"]["configuration"]["status"] == "up"


def test_build_runtime_readiness_report_keeps_core_ready_when_optional_services_are_down(monkeypatch):
    monkeypatch.setattr(bootstrap_module.config_module.settings, "app_env", "production")
    monkeypatch.setattr(
        bootstrap_module,
        "check_database_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_redis_readiness",
        lambda: {"ok": False, "status": "down", "detail": "redis offline"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_celery_broker_readiness",
        lambda: {"ok": False, "status": "down", "detail": "broker offline"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_configuration_readiness",
        lambda: {"ok": True, "status": "up"},
    )
    monkeypatch.setattr(
        bootstrap_module,
        "check_finalize_worker_readiness",
        lambda: {"ok": True, "status": "idle"},
    )

    report = bootstrap_module.build_runtime_readiness_report()

    assert report["status"] == "degraded"
    assert report["ready"] is True
    assert report["checks"]["redis"]["detail"] == "redis offline"
    assert report["checks"]["celeryBroker"]["detail"] == "broker offline"


def test_assert_startup_configuration_safe_blocks_unsafe_production(monkeypatch):
    monkeypatch.setattr(bootstrap_module.config_module.settings, "app_env", "production")
    monkeypatch.setattr(
        bootstrap_module,
        "check_configuration_readiness",
        lambda: {"ok": False, "status": "misconfigured", "issues": ["JWT_SECRET is weak"]},
    )

    try:
        bootstrap_module.assert_startup_configuration_safe()
    except RuntimeError as exc:
        assert "JWT_SECRET is weak" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Unsafe production configuration should fail startup")


def test_readiness_endpoint_returns_detailed_status(app, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_runtime_readiness_report",
        lambda: {
            "status": "ok",
            "ready": True,
            "environment": "production",
            "checks": {
                "database": {"ok": True, "status": "up"},
                "redis": {"ok": True, "status": "up"},
                "celeryBroker": {"ok": True, "status": "up"},
                "configuration": {"ok": True, "status": "up"},
            },
        },
    )
    monkeypatch.setattr(main_module.settings, "app_env", "production")

    client = TestClient(app)
    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["checks"]["database"]["status"] == "up"
    assert response.json()["checks"]["redis"]["status"] == "up"
    assert response.json()["checks"]["celeryBroker"]["status"] == "up"
    assert response.json()["checks"]["configuration"]["status"] == "up"


def test_readiness_endpoint_fail_opens_in_local_development(app, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_runtime_readiness_report",
        lambda: {
            "status": "degraded",
            "ready": False,
            "environment": "development",
            "checks": {
                "database": {"ok": True, "status": "up"},
                "redis": {"ok": False, "status": "down", "detail": "redis offline"},
                "celeryBroker": {"ok": False, "status": "down", "detail": "broker offline"},
                "configuration": {"ok": True, "status": "up"},
            },
        },
    )
    monkeypatch.setattr(main_module.settings, "app_env", "development")

    client = TestClient(app)
    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["detail"] == "redis offline"


def test_readiness_endpoint_returns_503_for_production_failures(app, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_runtime_readiness_report",
        lambda: {
            "status": "degraded",
            "ready": False,
            "environment": "production",
            "checks": {
                "database": {"ok": False, "status": "down", "detail": "db offline"},
                "redis": {"ok": True, "status": "up"},
                "celeryBroker": {"ok": True, "status": "up"},
                "configuration": {"ok": True, "status": "up"},
            },
        },
    )
    monkeypatch.setattr(main_module.settings, "app_env", "production")

    client = TestClient(app)
    response = client.get("/api/health/readiness")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"]["database"]["detail"] == "db offline"


def test_readiness_alias_returns_same_payload(app, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_runtime_readiness_report",
        lambda: {
            "status": "ok",
            "ready": True,
            "environment": "production",
            "checks": {
                "database": {"ok": True, "status": "up"},
                "redis": {"ok": True, "status": "up"},
                "celeryBroker": {"ok": True, "status": "up"},
                "configuration": {"ok": True, "status": "up"},
            },
        },
    )
    monkeypatch.setattr(main_module.settings, "app_env", "production")

    client = TestClient(app)
    response = client.get("/api/readiness")

    assert response.status_code == 200
    assert response.json()["checks"]["configuration"]["status"] == "up"


def test_metrics_endpoint_reports_request_counters(app):
    client = TestClient(app)

    client.get("/api/health")
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.json()["requestsTotal"] >= 2
    assert "averageDurationMs" in response.json()
