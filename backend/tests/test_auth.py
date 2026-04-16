from fastapi.testclient import TestClient


def test_health_route_exists(app):
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_returns_access_token(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "chit_owner"
    assert body["owner_id"] == 1
    assert body["has_subscriber_profile"] is True


def test_login_rejects_invalid_password(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_health_route_sets_local_dev_cors_headers(app):
    client = TestClient(app)
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
