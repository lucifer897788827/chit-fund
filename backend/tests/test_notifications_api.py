from fastapi.testclient import TestClient

from app.core.time import utcnow
from app.models.chit import ChitGroup, GroupMembership
from app.models.support import Notification
from app.models.user import Owner, User


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


def _create_other_owner(db_session, *, suffix: str = "1") -> Owner:
    other_user = User(
        email=f"other-owner-{suffix}@example.com",
        phone=f"7777777{suffix.zfill(3)}",
        password_hash="unused",
        role="chit_owner",
        is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()

    other_owner = Owner(
        user_id=other_user.id,
        display_name="Other Owner",
        business_name="Other Owner Chits",
        city="Coimbatore",
        state="Tamil Nadu",
        status="active",
    )
    db_session.add(other_owner)
    db_session.flush()
    return other_owner


def test_owner_notification_list_filters_cross_owner_rows(app, db_session):
    other_owner = _create_other_owner(db_session)

    visible = Notification(
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Visible notification",
        message="Visible to the current owner",
        status="pending",
        created_at=utcnow(),
    )
    hidden = Notification(
        user_id=1,
        owner_id=other_owner.id,
        channel="in_app",
        title="Hidden notification",
        message="Should not leak across owner rows",
        status="pending",
        created_at=utcnow(),
    )
    db_session.add_all([visible, hidden])
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/notifications", headers=_owner_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert [row["title"] for row in body] == ["Visible notification"]
    assert body[0]["readAt"] is None
    assert body[0]["sentAt"] is None

    paginated = client.get("/api/notifications?page=1&pageSize=1", headers=_owner_headers(client))
    assert paginated.status_code == 200
    paginated_body = paginated.json()
    assert paginated_body["page"] == 1
    assert paginated_body["pageSize"] == 1
    assert len(paginated_body["items"]) == 1


def test_subscriber_notification_list_uses_subscriber_owner_scope(app, db_session):
    other_owner = _create_other_owner(db_session)

    visible = Notification(
        user_id=2,
        owner_id=1,
        channel="in_app",
        title="Subscriber visible notification",
        message="Visible to the current subscriber",
        status="pending",
        created_at=utcnow(),
    )
    hidden = Notification(
        user_id=2,
        owner_id=other_owner.id,
        channel="in_app",
        title="Subscriber hidden notification",
        message="Should not leak across owner rows",
        status="pending",
        created_at=utcnow(),
    )
    db_session.add_all([visible, hidden])
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/notifications", headers=_subscriber_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert [row["title"] for row in body] == ["Subscriber visible notification"]


def test_subscriber_notification_list_allows_cross_owner_membership_scope(app, db_session):
    member_owner = _create_other_owner(db_session, suffix="2")
    hidden_owner = _create_other_owner(db_session, suffix="3")

    member_owner_group = ChitGroup(
        owner_id=member_owner.id,
        group_code="NOTIFY-MEMBER-001",
        title="Cross Owner Notifications Group",
        chit_value=300000,
        installment_amount=15000,
        member_count=10,
        cycle_count=10,
        cycle_frequency="monthly",
        visibility="private",
        start_date=utcnow().date(),
        first_auction_date=utcnow().date(),
        current_cycle_no=1,
        bidding_enabled=True,
        status="active",
    )
    db_session.add(member_owner_group)
    db_session.flush()

    db_session.add(
        GroupMembership(
            group_id=member_owner_group.id,
            subscriber_id=2,
            member_no=1,
            membership_status="active",
        )
    )
    db_session.flush()

    cross_owner_visible = Notification(
        user_id=2,
        owner_id=member_owner.id,
        channel="in_app",
        title="Cross owner visible notification",
        message="Visible because the subscriber belongs to this owner's chit group",
        status="pending",
        created_at=utcnow(),
    )
    hidden = Notification(
        user_id=2,
        owner_id=hidden_owner.id,
        channel="in_app",
        title="Cross owner hidden notification",
        message="Should stay hidden without a matching group membership",
        status="pending",
        created_at=utcnow(),
    )
    db_session.add_all([cross_owner_visible, hidden])
    db_session.commit()

    client = TestClient(app)
    headers = _subscriber_headers(client)

    response = client.get("/api/notifications", headers=headers)
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "Cross owner visible notification" in titles
    assert "Cross owner hidden notification" not in titles

    mark_read_response = client.patch(f"/api/notifications/{cross_owner_visible.id}/read", headers=headers)
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["status"] == "read"


def test_mark_notification_read_updates_read_at_and_blocks_cross_owner_rows(app, db_session):
    other_owner = _create_other_owner(db_session)

    readable = Notification(
        user_id=1,
        owner_id=1,
        channel="in_app",
        title="Unread notification",
        message="This should be markable",
        status="pending",
        created_at=utcnow(),
    )
    blocked = Notification(
        user_id=1,
        owner_id=other_owner.id,
        channel="in_app",
        title="Blocked notification",
        message="This should stay unread",
        status="pending",
        created_at=utcnow(),
    )
    db_session.add_all([readable, blocked])
    db_session.commit()

    client = TestClient(app)
    headers = _owner_headers(client)

    response = client.patch(f"/api/notifications/{readable.id}/read", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "read"
    assert response.json()["readAt"] is not None

    db_session.refresh(readable)
    assert readable.read_at is not None
    assert readable.status == "read"

    forbidden = client.patch(f"/api/notifications/{blocked.id}/read", headers=headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Notification does not belong to the current owner or subscriber"
