from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.external import ExternalChit


def test_create_external_chit(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/external-chits",
        json={
            "subscriberId": 2,
            "title": "Neighbourhood Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Neighbourhood Chit"
    external_chit = db_session.scalar(select(ExternalChit).where(ExternalChit.title == "Neighbourhood Chit"))
    assert external_chit is not None


def test_list_external_chits_for_subscriber(app):
    client = TestClient(app)
    create_response = client.post(
        "/api/external-chits",
        json={
            "subscriberId": 2,
            "title": "Neighbourhood Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
        },
    )
    assert create_response.status_code == 201
    response = client.get("/api/external-chits", params={"subscriberId": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Neighbourhood Chit"
