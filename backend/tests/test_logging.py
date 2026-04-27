import json
import logging

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, PlainFormatter, configure_logging, log_job_event, resolve_structured_logging
from app.main import app


def test_resolve_structured_logging_defaults_by_environment():
    assert resolve_structured_logging("production", None) is True
    assert resolve_structured_logging("prod", None) is True
    assert resolve_structured_logging("development", None) is False
    assert resolve_structured_logging("development", True) is True
    assert resolve_structured_logging("production", False) is False


def test_json_formatter_serializes_request_metadata():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http.request.completed",
        args=(),
        exc_info=None,
    )
    record.event = "http.request.completed"
    record.request_id = "req-123"
    record.method = "GET"
    record.path = "/api/health"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "http.request.completed"
    assert payload["request_id"] == "req-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/health"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5
    assert "timestamp" in payload
    assert payload["message"] == "http.request.completed"


def test_fastapi_emits_startup_and_request_logs_as_json(capsys, monkeypatch):
    configure_logging(app_env="development", structured_logging=True, level="INFO")
    monkeypatch.setattr("app.main.settings.app_env", "development")
    monkeypatch.setattr("app.main.bootstrap_database", lambda: None)

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-request-id": "req-abc"})

    assert response.status_code == 200

    captured_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    payloads = [json.loads(line) for line in captured_lines]
    events = [payload["event"] for payload in payloads if "event" in payload]

    assert "app.startup" in events
    completed = next(payload for payload in payloads if payload.get("event") == "http.request.completed")
    assert completed["request_id"] == "req-abc"
    assert completed["method"] == "GET"
    assert completed["path"] == "/api/health"
    assert completed["status_code"] == 200
    assert completed["app_env"] == "development"


def test_request_logging_returns_request_id_header(monkeypatch):
    configure_logging(app_env="development", structured_logging=True, level="INFO")
    monkeypatch.setattr("app.main.bootstrap_database", lambda: None)

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-request-id": "req-visible"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-visible"


def test_slow_request_logs_and_increments_metric(capsys, monkeypatch):
    from app import main as main_module

    configure_logging(app_env="development", structured_logging=True, level="INFO")
    monkeypatch.setattr("app.main.bootstrap_database", lambda: None)
    monkeypatch.setattr(main_module, "perf_counter", iter([10.0, 10.6, 11.0, 11.01]).__next__)
    with main_module._REQUEST_METRICS_LOCK:
        main_module._REQUEST_METRICS["requests_total"] = 0
        main_module._REQUEST_METRICS["errors_total"] = 0
        main_module._REQUEST_METRICS["duration_ms_total"] = 0.0
        main_module._REQUEST_METRICS["slow_requests_total"] = 0

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-request-id": "req-slow"})
        metrics_response = client.get("/api/metrics")

    assert response.status_code == 200
    assert metrics_response.json()["slowRequestsTotal"] == 1

    captured_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    payloads = [json.loads(line) for line in captured_lines]
    slow_log = next(payload for payload in payloads if payload.get("event") == "http.request.slow")
    assert slow_log["request_id"] == "req-slow"
    assert slow_log["path"] == "/api/health"
    assert slow_log["duration_ms"] == 600.0


def test_unhandled_exception_logs_request_context(capsys, monkeypatch):
    from app import main as main_module

    configure_logging(app_env="development", structured_logging=True, level="INFO")
    monkeypatch.setattr("app.main.bootstrap_database", lambda: None)

    route_path = "/api/test-error-logging"
    if not any(getattr(route, "path", None) == route_path for route in main_module.fastapi_app.router.routes):
        @main_module.fastapi_app.get(route_path)
        async def _test_error_logging_route(request: Request):
            request.state.user_id = 42
            raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(route_path, headers={"x-request-id": "req-error"})

    assert response.status_code == 500

    captured_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    payloads = [json.loads(line) for line in captured_lines]
    failure_log = next(payload for payload in payloads if payload.get("event") == "http.request.failed")
    assert failure_log["request_id"] == "req-error"
    assert failure_log["path"] == route_path
    assert failure_log["user_id"] == 42
    assert "RuntimeError: boom" in failure_log["exception"]


def test_log_job_event_emits_job_metadata_as_json(capsys):
    logger = configure_logging(app_env="development", structured_logging=True, level="INFO")

    log_job_event(
        logger,
        event="job.success",
        job_name="notifications.queue_payment_reminders",
        status="success",
        task_id="task-123",
        duration_ms=18.75,
        metadata={"resultCount": 4},
    )

    captured_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    payload = json.loads(captured_lines[-1])

    assert payload["event"] == "job.success"
    assert payload["job_name"] == "notifications.queue_payment_reminders"
    assert payload["status"] == "success"
    assert payload["task_id"] == "task-123"
    assert payload["duration_ms"] == 18.75
    assert payload["metadata"] == {"resultCount": 4}


def test_json_formatter_serializes_nested_job_metadata():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job.success",
        args=(),
        exc_info=None,
    )
    record.event = "job.success"
    record.job_name = "notifications.deliver_notification"
    record.status = "success"
    record.task_id = "task-123"
    record.duration_ms = 18.25
    record.metadata = {"notification_id": 42, "result": {"status": "sent", "count": 1}}

    payload = json.loads(formatter.format(record))

    assert payload["job_name"] == "notifications.deliver_notification"
    assert payload["status"] == "success"
    assert payload["task_id"] == "task-123"
    assert payload["metadata"]["notification_id"] == 42
    assert payload["metadata"]["result"]["status"] == "sent"
    assert payload["metadata"]["result"]["count"] == 1


def test_json_formatter_redacts_sensitive_extra_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth.failure",
        args=(),
        exc_info=None,
    )
    record.password = "secret"
    record.access_token = "jwt-token"
    record.metadata = {
        "Authorization": "Bearer jwt-token",
        "nested": {"refresh_token": "refresh-token"},
    }

    payload = json.loads(formatter.format(record))

    assert payload["password"] == "[REDACTED]"
    assert payload["access_token"] == "[REDACTED]"
    assert payload["metadata"]["Authorization"] == "[REDACTED]"
    assert payload["metadata"]["nested"]["refresh_token"] == "[REDACTED]"


def test_plain_formatter_includes_performance_context():
    formatter = PlainFormatter()
    record = logging.LogRecord(
        name="app.modules.admin.service",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="admin.performance",
        args=(),
        exc_info=None,
    )
    record.event = "admin.performance"
    record.endpoint = "/api/admin/users"
    record.user_id = 3
    record.duration_ms = 20.15
    record.db_query_ms = 2.5
    record.processing_ms = 17.65

    line = formatter.format(record)

    assert "endpoint=/api/admin/users" in line
    assert "user_id=3" in line
    assert "duration_ms=20.15" in line
    assert "db_query_ms=2.5" in line
    assert "processing_ms=17.65" in line
