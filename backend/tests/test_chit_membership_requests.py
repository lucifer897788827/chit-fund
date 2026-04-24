from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.chit import ChitGroup, GroupMembership, Installment, MembershipSlot
from app.models.user import Owner


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _active_public_group(db_session) -> ChitGroup:
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = ChitGroup(
        owner_id=owner.id,
        group_code="REQ-001",
        title="Request Group",
        chit_value=300000,
        installment_amount=15000,
        member_count=10,
        cycle_count=5,
        cycle_frequency="monthly",
        visibility="public",
        start_date=date(2026, 6, 1),
        first_auction_date=date(2026, 6, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def test_subscriber_can_request_and_owner_can_approve_membership(app, db_session):
    group = _active_public_group(db_session)
    client = TestClient(app)

    request_response = client.post(
        f"/api/chits/{group.id}/request",
        headers=_subscriber_headers(client),
    )
    assert request_response.status_code == 200
    membership_id = request_response.json()["membershipId"]
    assert request_response.json()["membershipStatus"] == "pending"

    owner_requests_response = client.get(
        "/api/chits/owner/requests",
        headers=_owner_headers(client),
    )
    assert owner_requests_response.status_code == 200
    assert owner_requests_response.json()[0]["membershipId"] == membership_id

    approve_response = client.post(
        f"/api/chits/{group.id}/approve-member",
        headers=_owner_headers(client),
        json={"membershipId": membership_id},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["membershipStatus"] == "active"
    assert approve_response.json()["slotCount"] == 1

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    slots = db_session.scalars(select(MembershipSlot).where(MembershipSlot.group_id == group.id)).all()
    installments = db_session.scalars(select(Installment).where(Installment.group_id == group.id)).all()
    assert membership is not None
    assert membership.membership_status == "active"
    assert len(slots) == 1
    assert len(installments) == 5


def test_owner_can_reject_membership_request(app, db_session):
    group = _active_public_group(db_session)
    client = TestClient(app)

    request_response = client.post(
        f"/api/chits/{group.id}/request",
        headers=_subscriber_headers(client),
    )
    membership_id = request_response.json()["membershipId"]

    reject_response = client.post(
        f"/api/chits/{group.id}/reject-member",
        headers=_owner_headers(client),
        json={"membershipId": membership_id},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["membershipStatus"] == "rejected"
    assert reject_response.json()["memberNo"] < 0

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    assert membership is not None
    assert membership.membership_status == "rejected"
    assert membership.member_no < 0


def test_subscriber_cannot_create_duplicate_pending_membership_request(app, db_session):
    group = _active_public_group(db_session)
    client = TestClient(app)
    headers = _subscriber_headers(client)

    first_response = client.post(f"/api/chits/{group.id}/request", headers=headers)
    second_response = client.post(f"/api/chits/{group.id}/request", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Membership request is already pending"
