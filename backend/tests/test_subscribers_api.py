from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.user import Subscriber


def _auth_headers(client: TestClient, phone: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _owner_headers(client: TestClient) -> dict[str, str]:
    return _auth_headers(client, "9999999999", "secret123")


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    return _auth_headers(client, "8888888888", "pass123")


def test_subscriber_crud_endpoints_are_owner_scoped_and_login_ready(app, db_session):
    client = TestClient(app)
    headers = _owner_headers(client)

    create_response = client.post(
        "/api/subscribers",
        headers=headers,
        json={
            "ownerId": 1,
            "fullName": "API Subscriber",
            "phone": "7777777000",
            "email": "api-subscriber@example.com",
            "password": "subscriber-api-pass",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "active"

    login_response = client.post(
        "/api/auth/login",
        json={"phone": "7777777000", "password": "subscriber-api-pass"},
    )
    assert login_response.status_code == 200

    list_response = client.get("/api/subscribers", headers=headers)
    assert list_response.status_code == 200
    assert any(row["id"] == created["id"] for row in list_response.json())

    paginated_response = client.get("/api/subscribers?page=1&pageSize=1", headers=headers)
    assert paginated_response.status_code == 200
    paginated = paginated_response.json()
    assert paginated["page"] == 1
    assert paginated["pageSize"] == 1
    assert paginated["totalCount"] >= 2
    assert len(paginated["items"]) == 1

    update_response = client.patch(
        f"/api/subscribers/{created['id']}",
        headers=headers,
        json={"fullName": "API Subscriber Updated", "phone": "7777777001"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["fullName"] == "API Subscriber Updated"
    assert update_response.json()["phone"] == "7777777001"

    delete_response = client.delete(f"/api/subscribers/{created['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"


def test_create_subscriber_rejects_duplicate_phone(app):
    client = TestClient(app)

    response = client.post(
        "/api/subscribers",
        headers=_owner_headers(client),
        json={
            "ownerId": 1,
            "fullName": "Duplicate Subscriber",
            "phone": "8888888888",
            "email": "duplicate@example.com",
            "password": "subscriber-api-pass",
        },
    )

    assert response.status_code == 409


def test_subscriber_can_self_join_active_group(app, db_session):
    group = ChitGroup(
        owner_id=1,
        group_code="JOIN-API-001",
        title="Join API Chit",
        chit_value=10000,
        installment_amount=1000,
        member_count=10,
        cycle_count=3,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.commit()

    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "8888888888"))
    assert subscriber is not None
    client = TestClient(app)

    response = client.post(
        f"/api/groups/{group.id}/join",
        headers=_subscriber_headers(client),
        json={"subscriberId": subscriber.id, "memberNo": 4},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subscriberId"] == subscriber.id
    assert body["memberNo"] == 4

    membership = db_session.get(GroupMembership, body["id"])
    assert membership is not None
    installments = db_session.scalars(
        select(Installment).where(Installment.membership_id == membership.id).order_by(Installment.cycle_no)
    ).all()
    assert len(installments) == 3
