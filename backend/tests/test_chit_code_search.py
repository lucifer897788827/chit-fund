from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.chit import ChitGroup, GroupMembership
from app.models.user import Owner, Subscriber, User


def _owner_headers(client: TestClient, *, phone: str = "9999999999", password: str = "secret123") -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "password": password},
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


def _create_group(
    db_session,
    *,
    owner_id: int,
    group_code: str,
    title: str,
    visibility: str = "private",
    status: str = "active",
) -> ChitGroup:
    group = ChitGroup(
        owner_id=owner_id,
        group_code=group_code,
        title=title,
        chit_value=400000,
        installment_amount=20000,
        member_count=10,
        cycle_count=5,
        cycle_frequency="monthly",
        visibility=visibility,
        start_date=date(2026, 7, 1),
        first_auction_date=date(2026, 7, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status=status,
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def _create_owner(db_session, *, email: str, phone: str, password: str, display_name: str) -> Owner:
    owner_user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="chit_owner",
        is_active=True,
    )
    db_session.add(owner_user)
    db_session.flush()
    owner = Owner(
        user_id=owner_user.id,
        display_name=display_name,
        business_name=f"{display_name} Chits",
        city="Madurai",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(owner)
    db_session.flush()
    owner_subscriber = Subscriber(
        user_id=owner_user.id,
        owner_id=owner.id,
        full_name="Owner Two",
        phone=owner_user.phone,
        email=owner_user.email,
        status="active",
    )
    db_session.add(owner_subscriber)
    db_session.commit()
    db_session.refresh(owner)
    return owner


def test_code_search_returns_active_matches_across_owners_and_visibilities(app, db_session):
    owner_one = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner_one is not None
    owner_two = _create_owner(
        db_session,
        email="owner-two@example.com",
        phone="7777777777",
        password="secret456",
        display_name="Owner Two",
    )
    owner_three = _create_owner(
        db_session,
        email="owner-three@example.com",
        phone="6666666666",
        password="secret789",
        display_name="Owner Three",
    )

    _create_group(
        db_session,
        owner_id=owner_one.id,
        group_code="JOIN-123",
        title="Owner One Private Match",
        visibility="private",
    )
    _create_group(
        db_session,
        owner_id=owner_two.id,
        group_code="join-123",
        title="Owner Two Public Match",
        visibility="public",
    )
    _create_group(
        db_session,
        owner_id=owner_three.id,
        group_code="JOIN-123",
        title="Inactive Match",
        visibility="public",
        status="draft",
    )
    _create_group(
        db_session,
        owner_id=owner_one.id,
        group_code="OTHER-999",
        title="Different Code",
        visibility="public",
    )

    client = TestClient(app)

    response = client.get("/api/chits/code/JOIN-123")

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload] == ["Owner Two Public Match"]
    assert all(item["status"] == "active" for item in payload)
    assert {item["visibility"] for item in payload} == {"public"}

def test_outsider_cannot_search_private_chit_by_code(app, db_session):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = _create_group(
        db_session,
        owner_id=owner.id,
        group_code="JOIN-404",
        title="Private Hidden Group",
        visibility="private",
    )

    client = TestClient(app)

    anonymous_response = client.get("/api/chits/code/join-404")
    subscriber_response = client.get("/api/chits/code/join-404", headers=_subscriber_headers(client))

    assert anonymous_response.status_code == 404
    assert subscriber_response.status_code == 404

    owner_response = client.get("/api/chits/code/join-404", headers=_owner_headers(client))
    assert owner_response.status_code == 200
    assert owner_response.json()[0]["id"] == group.id


def test_subscriber_can_search_public_code_request_membership_and_owner_can_approve(app, db_session):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = _create_group(
        db_session,
        owner_id=owner.id,
        group_code="JOIN-777",
        title="Code Search Group",
        visibility="public",
    )

    client = TestClient(app)
    subscriber_headers = _subscriber_headers(client)
    owner_headers = _owner_headers(client)

    search_response = client.get("/api/chits/code/join-777", headers=subscriber_headers)
    assert search_response.status_code == 200
    assert search_response.json()[0]["id"] == group.id

    request_response = client.post(
        f"/api/chits/{group.id}/request",
        headers=subscriber_headers,
    )
    assert request_response.status_code == 200
    membership_id = request_response.json()["membershipId"]
    assert request_response.json()["membershipStatus"] == "pending"

    approve_response = client.post(
        f"/api/chits/{group.id}/approve-member",
        headers=owner_headers,
        json={"membershipId": membership_id},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["membershipStatus"] == "active"

    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    assert membership is not None
    assert membership.membership_status == "active"


def test_invited_subscriber_can_search_private_chit_by_code(app, db_session):
    owner = db_session.scalar(select(Owner).where(Owner.id == 1))
    assert owner is not None
    group = _create_group(
        db_session,
        owner_id=owner.id,
        group_code="JOIN-INV",
        title="Invite Only Group",
        visibility="private",
    )

    invited_membership = GroupMembership(
        group_id=group.id,
        subscriber_id=2,
        member_no=1,
        membership_status="invited",
        prized_status="unprized",
        can_bid=False,
    )
    db_session.add(invited_membership)
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/chits/code/join-inv", headers=_subscriber_headers(client))

    assert response.status_code == 200
    assert response.json()[0]["id"] == group.id
