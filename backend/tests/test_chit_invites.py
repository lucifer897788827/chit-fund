from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.time import utcnow
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


def _assert_legacy_chit_headers(response) -> None:
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"]
    assert "/api/groups" in response.headers["Link"]
    assert "299" in response.headers["Warning"]


def _create_subscriber(client: TestClient, owner_headers: dict[str, str], *, suffix: str) -> tuple[int, dict[str, str]]:
    phone = f"77777777{suffix}"
    password = f"pass-{suffix}"
    response = client.post(
        "/api/subscribers",
        headers=owner_headers,
        json={
            "ownerId": 1,
            "fullName": f"Invite Subscriber {suffix}",
            "phone": phone,
            "email": f"invite-subscriber-{suffix}@example.com",
            "password": password,
        },
    )
    assert response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
    )
    assert login_response.status_code == 200
    return response.json()["id"], {"Authorization": f"Bearer {login_response.json()['access_token']}"}


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
    _assert_legacy_chit_headers(invite_response)
    membership_id = invite_response.json()["membershipId"]
    assert invite_response.json()["membershipStatus"] == "invited"

    dashboard_response = client.get(
        "/api/subscribers/dashboard",
        headers=_subscriber_headers(client),
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["memberships"][0]["membershipStatus"] == "invited"
    assert dashboard_response.json()["memberships"][0]["inviteStatus"] == "pending"

    accept_response = client.post(
        f"/api/chits/{group.id}/accept-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id},
    )
    assert accept_response.status_code == 200
    _assert_legacy_chit_headers(accept_response)
    assert accept_response.json()["membershipStatus"] == "active"
    assert accept_response.json()["slotCount"] == 1

    invite_audit_row = db_session.execute(
        text(
            """
            SELECT status, accepted_at, membership_id
            FROM group_invites
            WHERE membership_id = :membership_id
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"membership_id": membership_id},
    ).mappings().one()
    assert invite_audit_row["status"] == "accepted"
    assert invite_audit_row["accepted_at"] is not None
    assert invite_audit_row["membership_id"] == membership_id

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
    _assert_legacy_chit_headers(invite_response)
    membership_id = invite_response.json()["membershipId"]

    reject_response = client.post(
        f"/api/chits/{group.id}/reject-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id},
    )
    assert reject_response.status_code == 200
    _assert_legacy_chit_headers(reject_response)
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
    _assert_legacy_chit_headers(invite_response)
    assert invite_response.json()["detail"] == "Invites are only supported for private groups"


def test_expired_private_group_invite_is_visible_and_cannot_be_accepted(app, db_session):
    group = _private_group(db_session)
    client = TestClient(app)

    invite_response = client.post(
        f"/api/chits/{group.id}/invite",
        headers=_owner_headers(client),
        json={"phone": "8888888888"},
    )
    _assert_legacy_chit_headers(invite_response)
    membership_id = invite_response.json()["membershipId"]

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    assert membership is not None
    membership.joined_at = utcnow() - timedelta(days=8)
    db_session.commit()

    dashboard_response = client.get(
        "/api/subscribers/dashboard",
        headers=_subscriber_headers(client),
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["memberships"][0]["inviteStatus"] == "expired"
    assert dashboard_response.json()["memberships"][0]["inviteExpiresAt"] is not None

    accept_response = client.post(
        f"/api/chits/{group.id}/accept-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": membership_id},
    )
    assert accept_response.status_code == 409
    _assert_legacy_chit_headers(accept_response)
    assert accept_response.json()["detail"] == "Membership invite has expired"


def test_owner_can_list_group_invites_with_pending_accepted_expired_and_revoked_statuses(app, db_session):
    group = _private_group(db_session)
    client = TestClient(app)
    owner_headers = _owner_headers(client)

    pending_subscriber_id, _pending_headers = _create_subscriber(client, owner_headers, suffix="301")
    revoked_subscriber_id, _revoked_headers = _create_subscriber(client, owner_headers, suffix="302")
    expired_subscriber_id, _expired_headers = _create_subscriber(client, owner_headers, suffix="303")

    accepted_invite_response = client.post(
        f"/api/groups/{group.id}/invite",
        headers=owner_headers,
        json={"subscriberId": 2},
    )
    assert accepted_invite_response.status_code == 200
    accepted_invite_id = accepted_invite_response.json()["inviteId"]
    accepted_membership_id = accepted_invite_response.json()["membershipId"]

    accepted_response = client.post(
        f"/api/groups/{group.id}/accept-invite",
        headers=_subscriber_headers(client),
        json={"membershipId": accepted_membership_id},
    )
    assert accepted_response.status_code == 200

    pending_invite_response = client.post(
        f"/api/groups/{group.id}/invite",
        headers=owner_headers,
        json={"subscriberId": pending_subscriber_id},
    )
    assert pending_invite_response.status_code == 200
    pending_invite_id = pending_invite_response.json()["inviteId"]

    revoked_invite_response = client.post(
        f"/api/groups/{group.id}/invite",
        headers=owner_headers,
        json={"subscriberId": revoked_subscriber_id},
    )
    assert revoked_invite_response.status_code == 200
    revoked_invite_id = revoked_invite_response.json()["inviteId"]

    expired_invite_response = client.post(
        f"/api/groups/{group.id}/invite",
        headers=owner_headers,
        json={"subscriberId": expired_subscriber_id},
    )
    assert expired_invite_response.status_code == 200
    expired_invite_id = expired_invite_response.json()["inviteId"]

    revoke_response = client.post(
        f"/api/groups/{group.id}/invites/{revoked_invite_id}/revoke",
        headers=owner_headers,
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "revoked"
    assert revoke_response.json()["revokedAt"] is not None

    db_session.execute(
        text("UPDATE group_invites SET expires_at = :expires_at WHERE id = :invite_id"),
        {"expires_at": utcnow() - timedelta(days=1), "invite_id": expired_invite_id},
    )
    db_session.execute(
        text("UPDATE group_invites SET updated_at = :updated_at WHERE id = :invite_id"),
        {"updated_at": utcnow(), "invite_id": expired_invite_id},
    )
    db_session.commit()

    list_response = client.get(
        f"/api/groups/{group.id}/invites",
        headers=owner_headers,
    )
    assert list_response.status_code == 200

    invites_by_id = {item["inviteId"]: item for item in list_response.json()}
    assert invites_by_id[accepted_invite_id]["status"] == "accepted"
    assert invites_by_id[accepted_invite_id]["acceptedAt"] is not None
    assert invites_by_id[accepted_invite_id]["membershipStatus"] == "active"
    assert invites_by_id[pending_invite_id]["status"] == "pending"
    assert invites_by_id[pending_invite_id]["acceptedAt"] is None
    assert invites_by_id[revoked_invite_id]["status"] == "revoked"
    assert invites_by_id[revoked_invite_id]["revokedAt"] is not None
    assert invites_by_id[expired_invite_id]["status"] == "expired"
    assert invites_by_id[expired_invite_id]["expiresAt"] is not None
