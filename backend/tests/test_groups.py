from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.external import ExternalChit
from app.models.money import Payment
from app.models.user import Owner, Subscriber, User


def test_core_models_are_importable():
    assert User.__tablename__ == "users"
    assert Owner.__tablename__ == "owners"
    assert Subscriber.__tablename__ == "subscribers"
    assert ChitGroup.__tablename__ == "chit_groups"
    assert GroupMembership.__tablename__ == "group_memberships"
    assert ExternalChit.__tablename__ == "external_chits"


def test_create_subscriber_persists_profile(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/subscribers",
        json={
            "ownerId": 1,
            "fullName": "Subscriber Two",
            "phone": "7777777777",
            "email": "subscriber2@example.com",
        },
    )
    assert response.status_code == 201
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.phone == "7777777777"))
    assert subscriber is not None
    assert subscriber.full_name == "Subscriber Two"


def test_create_group_returns_owner_scoped_group(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/groups",
        json={
            "ownerId": 1,
            "groupCode": "MAY-001",
            "title": "May Monthly Chit",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
        },
    )
    assert response.status_code == 201
    assert response.json()["groupCode"] == "MAY-001"
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.group_code == "MAY-001"))
    assert group is not None
    assert group.title == "May Monthly Chit"


def test_list_groups_returns_owner_groups(app):
    client = TestClient(app)
    client.post(
        "/api/groups",
        json={
            "ownerId": 1,
            "groupCode": "LIST-001",
            "title": "List Group",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "memberCount": 10,
            "cycleCount": 10,
            "cycleFrequency": "monthly",
            "startDate": "2026-08-01",
            "firstAuctionDate": "2026-08-10",
        },
    )
    response = client.get("/api/groups", params={"ownerId": 1})
    assert response.status_code == 200
    assert any(group["groupCode"] == "LIST-001" for group in response.json())


def test_create_membership_generates_installments(app, db_session):
    client = TestClient(app)
    group_response = client.post(
        "/api/groups",
        json={
            "ownerId": 1,
            "groupCode": "JUN-001",
            "title": "June Monthly Chit",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]

    response = client.post(
        f"/api/groups/{group_id}/memberships",
        json={"subscriberId": 1, "memberNo": 1},
    )
    assert response.status_code == 201
    membership = db_session.scalar(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    )
    installments = db_session.scalars(
        select(Installment).where(Installment.group_id == group_id).order_by(Installment.cycle_no)
    ).all()
    assert membership is not None
    assert len(installments) == 5
    assert float(installments[0].due_amount) == 15000.0
    assert installments[0].cycle_no == 1


def test_create_auction_session_for_group(app, db_session):
    client = TestClient(app)
    group_response = client.post(
        "/api/groups",
        json={
            "ownerId": 1,
            "groupCode": "AUC-API-001",
            "title": "Auction Api Group",
            "chitValue": 300000,
            "installmentAmount": 15000,
            "memberCount": 20,
            "cycleCount": 5,
            "cycleFrequency": "monthly",
            "startDate": "2026-06-01",
            "firstAuctionDate": "2026-06-10",
        },
    )
    group_id = group_response.json()["id"]
    response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        json={"cycleNo": 1, "biddingWindowSeconds": 240},
    )
    assert response.status_code == 201
    assert response.json()["groupId"] == group_id
    assert response.json()["status"] == "open"


def test_record_payment_returns_recorded_status(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/payments",
        json={
            "ownerId": 1,
            "subscriberId": 2,
            "membershipId": None,
            "installmentId": None,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 25000,
            "paymentDate": "2026-05-10",
            "referenceNo": "UPI-001",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "recorded"
    payment = db_session.scalar(select(Payment))
    assert payment is not None
    assert float(payment.amount) == 25000.0
