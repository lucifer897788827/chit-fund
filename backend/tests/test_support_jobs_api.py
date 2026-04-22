from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.time import utcnow
from app.models.job_tracking import JobRun
from app.modules.support.service import prune_job_runs


def _owner_auth_headers(client: TestClient) -> dict[str, str]:
    login_response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_list_background_job_runs(app, db_session):
    db_session.add_all(
        [
            JobRun(task_name="notifications.queue_payment_reminders", task_id="task-1", owner_id=1, status="success", attempts=1),
            JobRun(task_name="auctions.auto_close_expired_sessions", task_id="task-2", owner_id=1, status="failed", attempts=2),
        ]
    )
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/support/jobs", headers=_owner_auth_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {row["taskName"] for row in payload} == {
        "notifications.queue_payment_reminders",
        "auctions.auto_close_expired_sessions",
    }

    paginated = client.get("/api/support/jobs?page=1&pageSize=1", headers=_owner_auth_headers(client))
    assert paginated.status_code == 200
    paginated_body = paginated.json()
    assert paginated_body["page"] == 1
    assert paginated_body["pageSize"] == 1
    assert len(paginated_body["items"]) == 1


def test_owner_can_list_background_job_runs_with_large_limit_is_capped(app, db_session):
    for index in range(205):
        db_session.add(
            JobRun(
                task_name="notifications.queue_payment_reminders",
                task_id=f"support-task-{index:03d}",
                owner_id=1,
                status="success",
                attempts=1,
            )
        )
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/support/jobs?limit=500", headers=_owner_auth_headers(client))

    assert response.status_code == 200
    assert len(response.json()) == 200


def test_prune_job_runs_removes_only_old_terminal_rows(app, db_session):
    old_success = JobRun(
        task_name="notifications.deliver_pending_notifications",
        task_id="cleanup-old-success",
        status="success",
        attempts=1,
        completed_at=utcnow() - timedelta(days=40),
    )
    old_failure = JobRun(
        task_name="notifications.deliver_notification",
        task_id="cleanup-old-failure",
        status="failed",
        attempts=2,
        failed_at=utcnow() - timedelta(days=35),
    )
    running = JobRun(
        task_name="auctions.auto_close_expired_sessions",
        task_id="cleanup-running",
        status="running",
        attempts=1,
        started_at=utcnow(),
    )
    recent_success = JobRun(
        task_name="system.health_ping",
        task_id="cleanup-recent-success",
        status="success",
        attempts=1,
        completed_at=utcnow() - timedelta(days=2),
    )
    db_session.add_all([old_success, old_failure, running, recent_success])
    db_session.commit()

    result = prune_job_runs(db_session, older_than_days=14, limit=100)

    assert result == {"deletedCount": 2, "cutoffDays": 14}
    remaining_ids = db_session.scalars(select(JobRun.task_id).order_by(JobRun.id.asc())).all()
    assert remaining_ids == ["cleanup-running", "cleanup-recent-success"]
