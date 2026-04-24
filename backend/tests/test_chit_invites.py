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


def _private_group(db_session) -> ChitGroup:
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = ChitGroup(
        owner_id=owner.id,
        group_code="INV-001",
        title="Invite Group",
        chit_value=400000,
        installment_amount=20000,
        member_count=10,
        cycle_count=5,
        cycle_frequency="monthly",
        visibility="private",
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


def _public_group(db_session) -> ChitGroup:
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = ChitGroup(
        owner_id=owner.id,
        group_code="INV-002",
        title="Public Invite Group",
        chit_value=400000,
        installment_amount=20000,
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


def test_owner_can_invite_subscriber_and_subscriber_can_accept(app, db_session):
    group = _private_group(db_session)
    client = TestClient(app)

    invite_response = client.post(
        f"/api/chits/{group.id}/invite",
        headers=_owner_headers(client),
        json={"phone": "8888888888"},
    )
    assert invite_response.status_code == 200
    membership_id = invite_response.json()["membershipId"]
    assert invite_response.json()["membershipStatus"] == "invited"

    dashboard_response = client.get(
        "/api/subscribers/dashboard",
        headers=_subscriber_headers(client),
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["memberships"][0]["membershipStatus"] == "invited"

    accept_response = client.post(
        f"/api/chits/{group.id}/accept-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["membershipStatus"] == "active"
    assert accept_response.json()["slotCount"] == 1

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    slots = db_session.scalars(select(MembershipSlot).where(MembershipSlot.group_id == group.id)).all()
    installments = db_session.scalars(select(Installment).where(Installment.group_id == group.id)).all()
    assert membership is not None
    assert membership.membership_status == "active"
    assert len(slots) == 1
    assert len(installments) == 5


def test_subscriber_can_reject_private_group_invite(app, db_session):
    group = _private_group(db_session)
    client = TestClient(app)

    invite_response = client.post(
        f"/api/chits/{group.id}/invite",
        headers=_owner_headers(client),
        json={"phone": "8888888888"},
    )
    membership_id = invite_response.json()["membershipId"]

    reject_response = client.post(
        f"/api/chits/{group.id}/reject-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["membershipStatus"] == "rejected"
    assert reject_response.json()["memberNo"] < 0

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    assert membership is not None
    assert membership.membership_status == "rejected"
    assert membership.member_no < 0


def test_owner_cannot_send_private_invite_for_public_group(app, db_session):
    group = _public_group(db_session)
    client = TestClient(app)

    invite_response = client.post(
        f"/api/chits/{group.id}/invite",
        headers=_owner_headers(client),
        json={"phone": "8888888888"},
    )
    assert invite_response.status_code == 400
    assert invite_response.json()["detail"] == "Invites are only supported for private groups"
