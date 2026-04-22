import logging

import pytest

from app.tasks import notification_tasks, system_tasks


class _RecordCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_system_task_logs_start_and_success_with_metadata_and_task_id(monkeypatch):
    monkeypatch.setattr(system_tasks, "_current_task_id", lambda: "task-123")
    handler = _RecordCaptureHandler()
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    try:
        result = system_tasks.queue_health_ping("ok")
    finally:
        logger.removeHandler(handler)

    assert result["status"] == "ok"

    records = [record for record in handler.records if record.name == "app" and record.job_name == "system.health_ping"]
    assert [record.getMessage() for record in records] == ["job.start", "job.success"]
    assert records[0].task_id == "task-123"
    assert records[0].metadata == {"message": "ok"}
    assert records[1].duration_ms is not None
    assert records[1].metadata["result_status"] == "ok"


def test_notification_task_logs_failure_with_duration_and_exception(monkeypatch):
    monkeypatch.setattr(notification_tasks, "_current_task_id", lambda: "task-999")
    monkeypatch.setattr(notification_tasks, "deliver_notification", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    handler = _RecordCaptureHandler()
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    try:
        with pytest.raises(RuntimeError):
            notification_tasks.queue_notification_delivery(42)
    finally:
        logger.removeHandler(handler)

    records = [
        record
        for record in handler.records
        if record.name == "app" and record.job_name == "notifications.deliver_notification"
    ]
    assert [record.getMessage() for record in records] == ["job.start", "job.failure"]
    assert records[0].task_id == "task-999"
    assert records[0].metadata == {"notification_id": 42}
    assert records[1].task_id == "task-999"
    assert records[1].duration_ms is not None
    assert records[1].metadata == {"notification_id": 42}
    assert records[1].exc_info is not None
