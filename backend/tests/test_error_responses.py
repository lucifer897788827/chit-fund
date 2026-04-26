from fastapi.testclient import TestClient


def test_http_exceptions_include_standard_error_envelope(app):
    client = TestClient(app)

    response = client.get("/api/groups/1/status")

    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"] == "Not authenticated"
    assert response.json()["detail"] == "Not authenticated"


def test_validation_errors_include_standard_error_envelope(app):
    client = TestClient(app)

    response = client.post("/api/auth/login", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]
    assert isinstance(body["detail"], list)
    assert body["detail"][0]["msg"]
