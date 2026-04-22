import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, configure_logging, log_job_event, resolve_structured_logging
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
