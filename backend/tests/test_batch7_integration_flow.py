from collections import Counter
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import Payout
from app.models.support import Notification
from app.models.job_tracking import JobRun
from app.models.user import Subscriber


def _login_headers(client: TestClient, phone: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_batch7_full_system_flow_covers_auth_group_membership_auction_payment_and_monitoring(app, db_session):
    client = TestClient(app)
    owner_headers = _login_headers(client, "9999999999", "secret123")
    subscriber_headers = _login_headers(client, "8888888888", "pass123")

    group_response = client.post(
        "/api/groups",
        headers=owner_headers,
        json={
            "ownerId": 1,
            "groupCode": "B7-FLOW-001",
            "title": "Batch 7 Integration Group",
            "chitValue": 200000,
            "installmentAmount": 10000,
            "memberCount": 12,
            "cycleCount": 3,
            "cycleFrequency": "monthly",
            "startDate": "2026-07-01",
            "firstAuctionDate": "2026-07-10",
        },
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    membership_response = client.post(
        f"/api/groups/{group_id}/memberships",
        headers=owner_headers,
        json={"subscriberId": 2, "memberNo": 4},
    )
    assert membership_response.status_code == 201
    membership_id = membership_response.json()["id"]

    auction_response = client.post(
        f"/api/groups/{group_id}/auction-sessions",
        headers=owner_headers,
        json={"cycleNo": 1, "biddingWindowSeconds": 180},
    )
    assert auction_response.status_code == 201
    session_id = auction_response.json()["id"]

    bid_response = client.post(
        f"/api/auctions/{session_id}/bids",
        headers=subscriber_headers,
        json={"membershipId": membership_id, "bidAmount": 12000, "idempotencyKey": "b7-flow-bid-001"},
    )
    assert bid_response.status_code == 200
    assert bid_response.json()["accepted"] is True

    finalize_response = client.post(f"/api/auctions/{session_id}/finalize", headers=owner_headers)
    assert finalize_response.status_code == 200
    assert finalize_response.json()["status"] == "finalized"

    db_session.expire_all()
    payout = db_session.scalar(select(Payout).where(Payout.auction_result_id.is_not(None)))
    assert payout is not None
    payout_id = payout.id
    assert payout.status == "pending"

    settle_response = client.post(
        f"/api/payments/payouts/{payout_id}/settle",
        headers=owner_headers,
        json={
            "referenceNo": "B7-SETTLE-001",
            "payoutMethod": "bank_transfer",
            "payoutDate": "2026-07-11",
        },
    )
    assert settle_response.status_code == 200
    assert settle_response.json()["status"] == "settled"

    db_session.expire_all()
    group = db_session.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    membership = db_session.scalar(select(GroupMembership).where(GroupMembership.id == membership_id))
    session = db_session.scalar(select(AuctionSession).where(AuctionSession.id == session_id))
    payout = db_session.scalar(select(Payout).where(Payout.id == payout_id))

    assert group is not None
    assert group.current_cycle_no == 2
    assert group.status == "active"
    assert membership is not None
    assert membership.prized_status == "prized"
    assert membership.prized_cycle_no == 1
    assert session is not None
    assert session.status == "finalized"
    assert payout is not None
    assert payout.status == "settled"
    assert payout.reference_no == "B7-SETTLE-001"

    notifications = db_session.scalars(select(Notification)).all()
    owner_titles = Counter(
        notification.title for notification in notifications if notification.user_id == 1
    )
    subscriber_titles = Counter(
        notification.title for notification in notifications if notification.user_id == 2
    )
    assert owner_titles == Counter(
        {
            "Auction finalized for cycle 1": 2,
            "Payout created for Subscriber One": 2,
            "Payout settled for Subscriber One": 2,
        }
    )
    assert subscriber_titles == owner_titles

    jobs = db_session.scalars(
        select(JobRun).where(JobRun.task_name == "notifications.deliver_notification")
    ).all()
    assert len(jobs) == 6
    assert {row.task_name for row in jobs} == {"notifications.deliver_notification"}
    assert {row.status for row in jobs} == {"success"}
    assert all(row.summary_json and "notification_id" in row.summary_json for row in jobs)

    support_jobs_response = client.get(
        "/api/support/jobs?taskName=notifications.deliver_notification&status=success",
        headers=owner_headers,
    )
    assert support_jobs_response.status_code == 200
    assert len(support_jobs_response.json()) == 6
