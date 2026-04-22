from types import SimpleNamespace

from app.core import database
from sqlalchemy import select

from app.models.job_tracking import JobRun
from app.modules.job_tracking.signals import task_failed_handler, task_started_handler, task_succeeded_handler


def test_celery_signal_handlers_record_job_lifecycle(app):
    sender = SimpleNamespace(name="notifications.deliver_notification")

    with database.SessionLocal() as db_session:
        task_started_handler(sender=sender, task_id="signal-task-1", args=("hello",), kwargs={"limit": 10})
        task_succeeded_handler(sender=sender, task_id="signal-task-1", result={"status": "ok"})

        job_run = db_session.scalar(select(JobRun).where(JobRun.task_id == "signal-task-1"))

        assert job_run is not None
        assert job_run.status == "completed"
        assert job_run.attempts == 1
        assert job_run.started_at is not None
        assert job_run.completed_at is not None


def test_celery_failure_handler_marks_job_failed(app):
    sender = SimpleNamespace(name="system.health_ping")

    with database.SessionLocal() as db_session:
        task_started_handler(sender=sender, task_id="signal-task-2", args=(), kwargs={})
        task_failed_handler(
            sender=sender,
            task_id="signal-task-2",
            exception=RuntimeError("boom"),
            args=(),
            kwargs={},
        )

        job_run = db_session.scalar(select(JobRun).where(JobRun.task_id == "signal-task-2"))

        assert job_run is not None
        assert job_run.status == "failed"
        assert job_run.failed_at is not None
        assert job_run.summary_json is not None
