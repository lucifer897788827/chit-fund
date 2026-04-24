from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import Owner, OwnerRequest, User


def _auth_headers(client: TestClient, phone: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_subscriber_can_request_owner_and_admin_can_approve(app, db_session):
    admin_user = User(
        email="admin@example.com",
        phone="7777777777",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    client = TestClient(app)
    subscriber_headers = _auth_headers(client, "8888888888", "pass123")
    create_response = client.post("/api/owner-requests", json={}, headers=subscriber_headers)

    assert create_response.status_code == 201
    assert create_response.json()["status"] == "pending"

    admin_headers = _auth_headers(client, "7777777777", "admin-secret")
    list_response = client.get("/api/admin/owner-requests", headers=admin_headers)

    assert list_response.status_code == 200
    assert any(item["userId"] == 2 and item["status"] == "pending" for item in list_response.json())

    request_id = create_response.json()["id"]
    approve_response = client.post(f"/api/admin/owner-requests/{request_id}/approve", headers=admin_headers)

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["ownerCreated"] is True

    owner_request = db_session.scalar(select(OwnerRequest).where(OwnerRequest.id == request_id))
    approved_owner = db_session.scalar(select(Owner).where(Owner.user_id == 2))
    subscriber_user = db_session.scalar(select(User).where(User.id == 2))

    assert owner_request is not None
    assert owner_request.status == "approved"
    assert approved_owner is not None
    assert subscriber_user is not None
    assert subscriber_user.role == "chit_owner"

    auth_me_response = client.get("/api/auth/me", headers=subscriber_headers)

    assert auth_me_response.status_code == 200
    assert auth_me_response.json()["role"] == "chit_owner"
    assert auth_me_response.json()["owner_id"] == approved_owner.id
    assert auth_me_response.json()["subscriber_id"] == 2
    assert auth_me_response.json()["user"]["roles"] == ["subscriber", "owner"]


def test_admin_can_reject_owner_request(app, db_session):
    admin_user = User(
        email="admin2@example.com",
        phone="6666666666",
        password_hash=hash_password("admin-secret"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    client = TestClient(app)
    subscriber_headers = _auth_headers(client, "8888888888", "pass123")
    create_response = client.post("/api/owner-requests", json={}, headers=subscriber_headers)
    request_id = create_response.json()["id"]

    admin_headers = _auth_headers(client, "6666666666", "admin-secret")
    reject_response = client.post(f"/api/admin/owner-requests/{request_id}/reject", headers=admin_headers)

    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert reject_response.json()["ownerCreated"] is False
    assert db_session.scalar(select(Owner).where(Owner.user_id == 2)) is None
