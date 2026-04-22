from fastapi.testclient import TestClient

from app.models.job_tracking import JobRun
from app.modules.job_tracking.service import start_job_run


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_list_job_runs_endpoint_returns_recent_jobs(app, db_session):
    first = start_job_run(
        db_session,
        task_name="notifications.deliver_notification",
        task_id="task-a",
        owner_id=1,
        summary={"arguments": {"argCount": 1}},
    )
    second = start_job_run(
        db_session,
        task_name="system.health_ping",
        task_id="task-b",
        owner_id=1,
        summary={"arguments": {"argCount": 0}},
    )
    second.status = "completed"
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/jobs", headers=_auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [second.id, first.id]
    assert body[0]["jobType"] == "system.health_ping"
    assert body[1]["summary"]["arguments"]["argCount"] == 1

    paginated = client.get("/api/jobs?page=1&pageSize=1", headers=_auth_headers(client))
    assert paginated.status_code == 200
    paginated_body = paginated.json()
    assert paginated_body["page"] == 1
    assert paginated_body["pageSize"] == 1
    assert len(paginated_body["items"]) == 1
    assert paginated_body["items"][0]["id"] == second.id


def test_list_job_runs_endpoint_caps_large_limits(app, db_session):
    for index in range(205):
        start_job_run(
            db_session,
            task_name="notifications.deliver_notification",
            task_id=f"task-{index:03d}",
            owner_id=1,
            summary={"arguments": {"argCount": index}},
        )

    client = TestClient(app)
    response = client.get("/api/jobs?limit=500", headers=_auth_headers(client))

    assert response.status_code == 200
    assert len(response.json()) == 200


def test_get_job_run_endpoint_returns_single_job(app, db_session):
    job_run = start_job_run(
        db_session,
        task_name="notifications.deliver_pending_notifications",
        task_id="task-c",
        owner_id=1,
        summary={"arguments": {"kwargKeys": ["limit"]}},
    )

    client = TestClient(app)
    response = client.get(f"/api/jobs/{job_run.id}", headers=_auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_run.id
    assert body["jobType"] == "notifications.deliver_pending_notifications"
    assert body["summary"]["arguments"]["kwargKeys"] == ["limit"]


def test_get_job_run_endpoint_rejects_another_owners_job(app, db_session):
    job_run = start_job_run(
        db_session,
        task_name="notifications.deliver_pending_notifications",
        task_id="task-cross-owner",
        owner_id=999,
        summary={"arguments": {"kwargKeys": ["limit"]}},
    )

    client = TestClient(app)
    response = client.get(f"/api/jobs/{job_run.id}", headers=_auth_headers(client))

    assert response.status_code == 403
    assert response.json()["detail"] == "Cannot access another owner's job run"
