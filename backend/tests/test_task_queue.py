from app.tasks import queue_cleanup_job_runs, queue_health_ping, queue_notification_placeholder


def test_queue_health_ping_returns_safe_status_payload():
    result = queue_health_ping()

    assert result == {
        "status": "ok",
        "task": "system.health_ping",
        "message": "ok",
    }


def test_queue_notification_placeholder_exposes_celery_style_delay():
    delayed = queue_notification_placeholder.delay(
        recipient="owner@example.com",
        subject="Auction finalized",
    )

    assert delayed["task"] == "system.notification_placeholder"
    assert delayed["status"] == "queued"
    assert delayed["recipient"] == "owner@example.com"
    assert delayed["subject"] == "Auction finalized"


def test_queue_cleanup_job_runs_exposes_safe_result_shape(monkeypatch):
    class FakeJobRun:
        id = 11

    monkeypatch.setattr(
        "app.tasks.system_tasks.prune_job_runs",
        lambda db, older_than_days=14, limit=500: {"deletedCount": 2, "cutoffDays": older_than_days},
    )
    monkeypatch.setattr("app.tasks.system_tasks._start_tracked_job", lambda *args, **kwargs: FakeJobRun())
    monkeypatch.setattr("app.tasks.system_tasks._complete_tracked_job", lambda *args, **kwargs: None)

    result = queue_cleanup_job_runs.delay(older_than_days=10, limit=50)

    assert result == {"deletedCount": 2, "cutoffDays": 10}
