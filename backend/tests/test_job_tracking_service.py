from app.core import database
from app.models.job_tracking import JobRun
from app.modules.job_tracking.service import complete_job_run, fail_job_run, list_job_runs, start_job_run


def test_start_job_run_creates_and_increments_attempts(app):
    with database.SessionLocal() as db_session:
        job_run = start_job_run(
            db_session,
            task_name="notifications.deliver_notification",
            task_id="task-123",
            summary={"arguments": {"argCount": 1}},
        )

        assert job_run.status == "running"
        assert job_run.attempts == 1
        assert job_run.started_at is not None

        retried_job_run = start_job_run(
            db_session,
            task_name="notifications.deliver_notification",
            task_id="task-123",
            summary={"arguments": {"kwargKeys": ["notification_id"]}},
        )

        assert retried_job_run.id == job_run.id
        assert retried_job_run.attempts == 2

        stored = db_session.get(JobRun, job_run.id)
        assert stored is not None
        assert stored.status == "running"


def test_complete_and_fail_job_run_update_status_and_summary(app):
    with database.SessionLocal() as db_session:
        started = start_job_run(
            db_session,
            task_name="system.health_ping",
            task_id="task-456",
            summary={"arguments": {"argCount": 0}},
        )

        completed = complete_job_run(
            db_session,
            task_name="system.health_ping",
            task_id="task-456",
            summary={"result": {"status": "ok"}},
        )

        assert completed.id == started.id
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert list_job_runs(db_session, task_name="system.health_ping")[0]["summary"]["result"]["status"] == "ok"

        failed = fail_job_run(
            db_session,
            task_name="system.health_ping",
            task_id="task-789",
            summary={"error": "boom", "errorType": "RuntimeError"},
        )

        assert failed.status == "failed"
        assert failed.failed_at is not None
