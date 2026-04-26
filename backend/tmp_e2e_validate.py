import json
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.user import Owner, Subscriber, User
from app.modules.groups.slot_service import create_membership_slots

BASE = "http://127.0.0.1:8015"
TIMEOUT = 30
seed = int(time.time()) % 1000000


def phone(n: int) -> str:
    return f"7{seed:06d}{n:03d}"


PHONES = {
    "foundation": phone(1),
    "requester": phone(2),
    "private_invitee": phone(3),
    "public_bidder": phone(4),
    "journey_owner": phone(5),
    "journey_member_1": phone(6),
    "journey_member_2": phone(7),
    "admin": phone(8),
}
PASSWORD = "Pass12345!"

results = []
context = {}


def fail(msg: str):
    raise AssertionError(msg)


def check(condition: bool, msg: str):
    if not condition:
        fail(msg)


def api(
    method: str,
    path: str,
    *,
    token: str | None = None,
    origin: str | None = None,
    expected: int | None = None,
    **kwargs,
):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    response = requests.request(method, BASE + path, headers=headers, timeout=TIMEOUT, **kwargs)
    if expected is not None and response.status_code != expected:
        detail = response.text[:500]
        fail(f"{method} {path} expected {expected}, got {response.status_code}: {detail}")
    return response


def signup(name: str, phone_number: str):
    email = f"{phone_number}@example.com"
    response = api(
        "POST",
        "/api/auth/signup",
        json={
            "fullName": name,
            "phone": phone_number,
            "email": email,
            "password": PASSWORD,
        },
        expected=201,
    )
    return response.json()


def login(phone_number: str):
    response = api("POST", "/api/auth/login", json={"phone": phone_number, "password": PASSWORD}, expected=200)
    return response.json()


def auth_me(token: str):
    return api("GET", "/api/auth/me", token=token, expected=200).json()


def create_admin_user():
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.phone == PHONES["admin"]))
        if existing is None:
            user = User(
                email=f"{PHONES['admin']}@example.com",
                phone=PHONES["admin"],
                password_hash=hash_password(PASSWORD),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()


def insert_owner_profile(phone_number: str, *, display_name: str):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone_number))
        check(user is not None, f"user missing for owner insert: {phone_number}")
        owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
        if owner is None:
            owner = Owner(
                user_id=user.id,
                display_name=display_name,
                business_name=f"{display_name} Chits",
                city="Chennai",
                state="Tamil Nadu",
                status="active",
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
        return owner.id, user.id


def fetch_subscriber_id(phone_number: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone_number))
        check(user is not None, f"user missing for subscriber lookup: {phone_number}")
        subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
        check(subscriber is not None, f"subscriber missing for {phone_number}")
        return subscriber.id


def fetch_user_id(phone_number: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone_number))
        check(user is not None, f"user missing for lookup: {phone_number}")
        return user.id


def create_open_auction_session(group_id: int, owner_user_id: int):
    with SessionLocal() as db:
        group = db.get(ChitGroup, group_id)
        check(group is not None, f"group missing for auction session {group_id}")
        session = AuctionSession(
            group_id=group_id,
            cycle_no=group.current_cycle_no,
            scheduled_start_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            actual_start_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            bidding_window_seconds=180,
            status="open",
            opened_by_user_id=owner_user_id,
            min_bid_value=0,
            max_bid_value=int(group.chit_value),
            min_increment=1,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id


def add_extra_slot(membership_id: int):
    with SessionLocal() as db:
        membership = db.get(GroupMembership, membership_id)
        check(membership is not None, f"membership missing for slot allocation {membership_id}")
        create_membership_slots(db, membership, slot_count=1)
        db.commit()


def get_membership(group_id: int, subscriber_id: int):
    with SessionLocal() as db:
        membership = db.scalar(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.subscriber_id == subscriber_id,
            )
        )
        check(membership is not None, f"membership missing for group {group_id} subscriber {subscriber_id}")
        return {
            "id": membership.id,
            "status": membership.membership_status,
            "member_no": membership.member_no,
        }


def get_first_installment(membership_id: int):
    with SessionLocal() as db:
        installment = db.scalar(
            select(Installment)
            .where(Installment.membership_id == membership_id)
            .order_by(Installment.cycle_no.asc(), Installment.id.asc())
        )
        check(installment is not None, f"installment missing for membership {membership_id}")
        return {
            "id": installment.id,
            "cycle_no": installment.cycle_no,
            "due_amount": int(installment.due_amount),
            "balance_amount": int(installment.balance_amount),
        }


def wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.1, description: str = "condition"):
    deadline = time.perf_counter() + timeout
    last_value = None
    while time.perf_counter() < deadline:
        try:
            last_value = predicate()
        except AssertionError:
            last_value = None
        if last_value:
            return last_value
        time.sleep(interval)
    fail(f"Timed out waiting for {description}")


def run_batch(name, fn):
    start = time.perf_counter()
    details = fn()
    results.append(
        {
            "batch": name,
            "status": "PASS",
            "details": details or {},
            "durationMs": round((time.perf_counter() - start) * 1000, 2),
        }
    )


def batch1():
    signup("Foundation User", PHONES["foundation"])
    login_body = login(PHONES["foundation"])
    me_body = auth_me(login_body["access_token"])
    check(me_body["roles"] == ["subscriber"], f"unexpected foundation roles: {me_body['roles']}")
    refresh_body = api("POST", "/api/auth/refresh", json={"refresh_token": login_body["refresh_token"]}, expected=200).json()
    logout_response = api(
        "POST",
        "/api/auth/logout",
        token=refresh_body["access_token"],
        json={"refresh_token": refresh_body["refresh_token"]},
        expected=204,
    )
    check(logout_response.status_code == 204, "logout did not return 204")
    revoked = api("POST", "/api/auth/refresh", json={"refresh_token": refresh_body["refresh_token"]}, expected=401)
    return {
        "meRoles": me_body["roles"],
        "loginRole": login_body["role"],
        "refreshRole": refresh_body["role"],
        "revokedStatus": revoked.status_code,
    }


def batch2():
    foundation_login = login(PHONES["foundation"])
    initial_me = auth_me(foundation_login["access_token"])
    check(initial_me["roles"] == ["subscriber"], f"expected subscriber before owner insert, got {initial_me['roles']}")
    owner_id, owner_user_id = insert_owner_profile(PHONES["foundation"], display_name="Foundation Owner")
    owner_login = login(PHONES["foundation"])
    owner_me = auth_me(owner_login["access_token"])
    check(owner_me["roles"] == ["subscriber", "owner"], f"owner roles not derived: {owner_me['roles']}")
    check(owner_me["role"] == "chit_owner", f"owner primary role stale: {owner_me['role']}")
    create_admin_user()
    admin_login = login(PHONES["admin"])
    admin_me = auth_me(admin_login["access_token"])
    check(admin_me["roles"] == ["admin"], f"admin roles incorrect: {admin_me['roles']}")
    context["ownerToken"] = owner_login["access_token"]
    context["ownerId"] = owner_id
    context["ownerUserId"] = owner_user_id
    context["adminToken"] = admin_login["access_token"]
    return {
        "ownerRoles": owner_me["roles"],
        "ownerRole": owner_me["role"],
        "adminRoles": admin_me["roles"],
    }


def batch3():
    signup("Requester Subscriber", PHONES["requester"])
    requester_login = login(PHONES["requester"])
    requester_dashboard = api("GET", "/api/subscribers/dashboard", token=requester_login["access_token"], expected=200).json()
    owner_dashboard = api("GET", "/api/reporting/owner/dashboard", token=context["ownerToken"], expected=200).json()
    owner_on_subscriber = api("GET", "/api/subscribers/dashboard", token=context["ownerToken"], expected=403)
    context["requesterToken"] = requester_login["access_token"]
    context["requesterSubscriberId"] = fetch_subscriber_id(PHONES["requester"])
    return {
        "subscriberDashboardKeys": sorted(requester_dashboard.keys()),
        "ownerDashboardKeys": sorted(owner_dashboard.keys())[:5],
        "ownerSubscriberStatus": owner_on_subscriber.status_code,
    }


def batch4():
    stamp = datetime.now().strftime("%H%M%S")
    public_payload = {
        "ownerId": context["ownerId"],
        "groupCode": f"PUB-{stamp}",
        "title": f"Public Validation {stamp}",
        "chitValue": 10000,
        "installmentAmount": 1000,
        "memberCount": 3,
        "cycleCount": 1,
        "cycleFrequency": "monthly",
        "visibility": "public",
        "startDate": "2026-05-01",
        "firstAuctionDate": "2026-05-10",
    }
    private_payload = {
        "ownerId": context["ownerId"],
        "groupCode": f"PRI-{stamp}",
        "title": f"Private Validation {stamp}",
        "chitValue": 10000,
        "installmentAmount": 1000,
        "memberCount": 3,
        "cycleCount": 1,
        "cycleFrequency": "monthly",
        "visibility": "private",
        "startDate": "2026-05-01",
        "firstAuctionDate": "2026-05-10",
    }
    public_group = api("POST", "/api/groups", token=context["ownerToken"], json=public_payload, expected=201).json()
    private_group = api("POST", "/api/groups", token=context["ownerToken"], json=private_payload, expected=201).json()
    public_listing = api("GET", "/api/chits/public", expected=200).json()
    public_codes = {item["groupCode"] for item in public_listing}
    check(public_group["status"] == "active", f"public group status not active: {public_group['status']}")
    check(public_group["groupCode"] in public_codes, "public group missing from public listing")
    check(private_group["groupCode"] not in public_codes, "private group leaked into public listing")
    context["publicGroup"] = public_group
    context["privateGroup"] = private_group
    return {
        "publicGroupStatus": public_group["status"],
        "privateGroupStatus": private_group["status"],
        "publicListingContainsPublic": public_group["groupCode"] in public_codes,
        "publicListingContainsPrivate": private_group["groupCode"] in public_codes,
    }


def batch5():
    request_response = api(
        "POST",
        f"/api/chits/{context['publicGroup']['id']}/request",
        token=context["requesterToken"],
        expected=200,
    ).json()
    check(request_response["membershipStatus"] == "pending", f"request status not pending: {request_response}")
    owner_requests = api("GET", "/api/chits/owner/requests", token=context["ownerToken"], expected=200).json()
    membership_id = request_response["membershipId"]
    check(any(item["membershipId"] == membership_id for item in owner_requests), "pending membership not visible to owner")
    approve_response = api(
        "POST",
        f"/api/chits/{context['publicGroup']['id']}/approve-member",
        token=context["ownerToken"],
        json={"membershipId": membership_id},
        expected=200,
    ).json()
    check(approve_response["membershipStatus"] == "active", f"approved membership not active: {approve_response}")
    requester_dashboard = api("GET", "/api/subscribers/dashboard", token=context["requesterToken"], expected=200).json()
    check(
        any(item["membershipId"] == membership_id and item["membershipStatus"] == "active" for item in requester_dashboard["memberships"]),
        "approved membership missing from subscriber dashboard",
    )

    signup("Private Invitee", PHONES["private_invitee"])
    private_invitee_login = login(PHONES["private_invitee"])
    invite_response = api(
        "POST",
        f"/api/chits/{context['privateGroup']['id']}/invite",
        token=context["ownerToken"],
        json={"phone": PHONES["private_invitee"]},
        expected=200,
    ).json()
    check(invite_response["membershipStatus"] == "invited", f"invite status not invited: {invite_response}")
    invite_dashboard = api("GET", "/api/subscribers/dashboard", token=private_invitee_login["access_token"], expected=200).json()
    check(
        any(item["membershipId"] == invite_response["membershipId"] and item["membershipStatus"] == "invited" for item in invite_dashboard["memberships"]),
        "invite missing from subscriber dashboard",
    )
    accept_response = api(
        "POST",
        f"/api/chits/{context['privateGroup']['id']}/accept-invite",
        token=private_invitee_login["access_token"],
        json={"membershipId": invite_response["membershipId"]},
        expected=200,
    ).json()
    check(accept_response["membershipStatus"] == "active", f"invite accept not active: {accept_response}")
    context["requesterMembershipId"] = membership_id
    context["privateInviteeToken"] = private_invitee_login["access_token"]
    context["privateInviteeSubscriberId"] = fetch_subscriber_id(PHONES["private_invitee"])
    return {
        "requestedMembershipId": membership_id,
        "approvedStatus": approve_response["membershipStatus"],
        "invitedMembershipId": invite_response["membershipId"],
        "acceptedStatus": accept_response["membershipStatus"],
    }


def batch6():
    signup("Public Bidder", PHONES["public_bidder"])
    public_bidder_login = login(PHONES["public_bidder"])
    public_request = api(
        "POST",
        f"/api/chits/{context['publicGroup']['id']}/request",
        token=public_bidder_login["access_token"],
        expected=200,
    ).json()
    check(public_request["membershipStatus"] == "pending", f"public bidder request not pending: {public_request}")
    api(
        "POST",
        f"/api/chits/{context['publicGroup']['id']}/approve-member",
        token=context["ownerToken"],
        json={"membershipId": public_request["membershipId"]},
        expected=200,
    )
    bidder_subscriber_id = fetch_subscriber_id(PHONES["public_bidder"])
    bidder_membership = get_membership(context["publicGroup"]["id"], bidder_subscriber_id)
    add_extra_slot(context["requesterMembershipId"])
    session_id = create_open_auction_session(context["publicGroup"]["id"], context["ownerUserId"])

    invalid_bid = api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=context["requesterToken"],
        json={"membershipId": context["requesterMembershipId"], "bidAmount": -1, "idempotencyKey": f"invalid-{seed}"},
        expected=409,
    )
    bid_one = api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=context["requesterToken"],
        json={"membershipId": context["requesterMembershipId"], "bidAmount": 1100, "idempotencyKey": f"bid-one-{seed}"},
        expected=200,
    ).json()
    bid_two = api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=context["requesterToken"],
        json={"membershipId": context["requesterMembershipId"], "bidAmount": 1200, "idempotencyKey": f"bid-two-{seed}"},
        expected=200,
    ).json()
    bid_three = api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=public_bidder_login["access_token"],
        json={"membershipId": bidder_membership["id"], "bidAmount": 1300, "idempotencyKey": f"bid-three-{seed}"},
        expected=200,
    ).json()

    started = time.perf_counter()
    finalize_one = api("POST", f"/api/auctions/{session_id}/finalize", token=context["ownerToken"], expected=200).json()
    finalize_duration_ms = round((time.perf_counter() - started) * 1000, 2)
    started = time.perf_counter()
    finalize_two = api("POST", f"/api/auctions/{session_id}/finalize", token=context["ownerToken"], expected=200).json()
    finalize_again_ms = round((time.perf_counter() - started) * 1000, 2)

    check(finalize_duration_ms < 60000, f"finalize took too long: {finalize_duration_ms}ms")
    check(finalize_again_ms < 60000, f"idempotent finalize took too long: {finalize_again_ms}ms")
    check(finalize_one["resultSummary"]["winnerMembershipId"] == bidder_membership["id"], f"wrong winner: {finalize_one['resultSummary']}")
    check(finalize_two["resultSummary"]["auctionResultId"] == finalize_one["resultSummary"]["auctionResultId"], "finalize not idempotent")

    payouts = wait_until(
        lambda: (
            lambda body: body if any(item["membershipId"] == bidder_membership["id"] for item in (body["items"] if isinstance(body, dict) and "items" in body else body)) else None
        )(
            api(
                "GET",
                f"/api/payments/payouts?groupId={context['publicGroup']['id']}",
                token=context["ownerToken"],
                expected=200,
            ).json()
        ),
        description="auction payout creation",
    )
    payout_items = payouts["items"] if isinstance(payouts, dict) and "items" in payouts else payouts
    check(any(item["membershipId"] == bidder_membership["id"] for item in payout_items), "payout missing after finalize")

    owner_notifications = wait_until(
        lambda: (
            lambda body: body if len(body["items"] if isinstance(body, dict) and "items" in body else body) > 0 else None
        )(
            api("GET", "/api/notifications", token=context["ownerToken"], expected=200).json()
        ),
        description="owner auction notifications",
    )
    bidder_notifications = wait_until(
        lambda: (
            lambda body: body if len(body["items"] if isinstance(body, dict) and "items" in body else body) > 0 else None
        )(
            api("GET", "/api/notifications", token=public_bidder_login["access_token"], expected=200).json()
        ),
        description="winner auction notifications",
    )
    owner_notification_items = owner_notifications["items"] if isinstance(owner_notifications, dict) and "items" in owner_notifications else owner_notifications
    bidder_notification_items = bidder_notifications["items"] if isinstance(bidder_notifications, dict) and "items" in bidder_notifications else bidder_notifications
    check(len(owner_notification_items) > 0, "owner notifications missing after auction finalize")
    check(len(bidder_notification_items) > 0, "winner notifications missing after auction finalize")

    context["publicBidderToken"] = public_bidder_login["access_token"]
    context["publicBidderSubscriberId"] = bidder_subscriber_id
    context["auctionSessionId"] = session_id
    return {
        "invalidBidStatus": invalid_bid.status_code,
        "acceptedBidIds": [bid_one["bidId"], bid_two["bidId"], bid_three["bidId"]],
        "winnerMembershipId": finalize_one["resultSummary"]["winnerMembershipId"],
        "finalizeMs": finalize_duration_ms,
        "finalizeAgainMs": finalize_again_ms,
        "payoutCount": len(payout_items),
    }


def batch7():
    installment = get_first_installment(context["requesterMembershipId"])
    initial_outstanding = int(installment["balance_amount"])
    check(initial_outstanding > 1, f"installment must have room for a partial payment: {installment}")
    partial_amount = min(600, initial_outstanding - 1)
    remaining_after_partial = initial_outstanding - partial_amount
    partial = api(
        "POST",
        "/api/payments",
        token=context["ownerToken"],
        json={
            "ownerId": context["ownerId"],
            "subscriberId": context["requesterSubscriberId"],
            "membershipId": context["requesterMembershipId"],
            "installmentId": installment["id"],
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": partial_amount,
            "paymentDate": "2026-05-10",
            "referenceNo": f"PAY-PART-{seed}",
        },
        expected=201,
    ).json()
    balances_after_partial = api(
        "GET",
        f"/api/payments/balances?subscriberId={context['requesterSubscriberId']}&groupId={context['publicGroup']['id']}",
        token=context["ownerToken"],
        expected=200,
    ).json()
    balance_item = balances_after_partial[0] if isinstance(balances_after_partial, list) else balances_after_partial["items"][0]
    check(partial["installmentStatus"] == "partial", f"partial payment did not mark installment partial: {partial}")
    check(int(balance_item["outstandingAmount"]) == remaining_after_partial, f"unexpected outstanding after partial: {balance_item}")
    check(int(balance_item["nextDueAmount"]) == remaining_after_partial, f"unexpected next due after partial: {balance_item}")

    full = api(
        "POST",
        "/api/payments",
        token=context["ownerToken"],
        json={
            "ownerId": context["ownerId"],
            "subscriberId": context["requesterSubscriberId"],
            "membershipId": context["requesterMembershipId"],
            "installmentId": installment["id"],
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": remaining_after_partial,
            "paymentDate": "2026-05-11",
            "referenceNo": f"PAY-FULL-{seed}",
        },
        expected=201,
    ).json()
    balances_after_full = api(
        "GET",
        f"/api/payments/balances?subscriberId={context['requesterSubscriberId']}&groupId={context['publicGroup']['id']}",
        token=context["ownerToken"],
        expected=200,
    ).json()
    balance_item_full = balances_after_full[0] if isinstance(balances_after_full, list) else balances_after_full["items"][0]
    decimal_reject = api(
        "POST",
        "/api/payments",
        token=context["ownerToken"],
        json={
            "ownerId": context["ownerId"],
            "subscriberId": context["requesterSubscriberId"],
            "membershipId": context["requesterMembershipId"],
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 1.5,
            "paymentDate": "2026-05-12",
            "referenceNo": f"PAY-DEC-{seed}",
        },
        expected=422,
    )
    check(full["installmentStatus"] == "paid", f"full payment did not clear installment: {full}")
    check(int(balance_item_full["outstandingAmount"]) == 0, f"unexpected outstanding after full payment: {balance_item_full}")
    return {
        "partialOutstanding": balance_item["outstandingAmount"],
        "finalOutstanding": balance_item_full["outstandingAmount"],
        "decimalRejectStatus": decimal_reject.status_code,
    }


def batch8():
    create_external = api(
        "POST",
        "/api/external-chits",
        token=context["requesterToken"],
        json={
            "title": "Integration External Chit",
            "name": "Integration Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 12,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
        expected=201,
    ).json()
    chit_id = create_external["id"]
    entry_one = api(
        "POST",
        f"/api/external-chits/{chit_id}/entries",
        token=context["requesterToken"],
        json={
            "entryType": "paid",
            "entryDate": "2026-04-05",
            "amount": 20000,
            "description": "Month one ledger entry",
            "monthNumber": 1,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
        expected=201,
    ).json()
    entry_two = api(
        "POST",
        f"/api/external-chits/{chit_id}/entries",
        token=context["requesterToken"],
        json={
            "entryType": "won",
            "entryDate": "2026-04-10",
            "amount": 18000,
            "description": "Month two ledger entry",
            "monthNumber": 2,
            "bidAmount": 18000,
            "winnerType": "SELF",
        },
        expected=201,
    ).json()
    entry_three = api(
        "POST",
        f"/api/external-chits/{chit_id}/entries",
        token=context["requesterToken"],
        json={
            "entryType": "paid",
            "entryDate": "2026-04-15",
            "amount": 15000,
            "description": "Month three ledger entry",
            "monthNumber": 3,
            "bidAmount": 15000,
            "winnerType": "OTHER",
            "myPayable": 16800,
        },
        expected=201,
    ).json()
    summary = api("GET", f"/api/external-chits/{chit_id}/summary", token=context["requesterToken"], expected=200).json()
    check(entry_three["isPayableOverridden"] is True, f"override flag missing: {entry_three}")
    check(
        summary == {"totalPaid": 49200, "totalReceived": 76200, "profit": 27000, "winningMonth": 2},
        f"unexpected external summary: {summary}",
    )
    return {
        "entryOneSharePerSlot": entry_one["sharePerSlot"],
        "entryTwoPayout": entry_two["myPayout"],
        "overrideFlag": entry_three["isPayableOverridden"],
        "summary": summary,
    }


def batch9():
    readiness = api("GET", "/api/health/readiness", expected=200)
    health = api("GET", "/api/health", expected=200)
    db_test = api("GET", "/api/db-test", expected=200)
    cors = api("GET", "/api/health", origin="http://localhost:3000", expected=200)
    readiness_body = readiness.json()
    cors_header = cors.headers.get("access-control-allow-origin")
    check(cors_header is not None and cors_header != "", "missing CORS allow origin header")
    check(db_test.json()["database"] == "connected", f"db test failed: {db_test.text}")
    return {
        "readiness": readiness_body,
        "health": health.json(),
        "dbTest": db_test.json(),
        "corsAllowOrigin": cors_header,
    }


def batch10():
    signup("Journey Owner Candidate", PHONES["journey_owner"])
    journey_login = login(PHONES["journey_owner"])
    owner_request = api("POST", "/api/owner-requests", token=journey_login["access_token"], json={}, expected=201).json()
    approved = api(
        "POST",
        f"/api/admin/owner-requests/{owner_request['id']}/approve",
        token=context["adminToken"],
        expected=200,
    ).json()
    check(approved["status"] == "approved", f"owner request not approved: {approved}")
    journey_owner_login = login(PHONES["journey_owner"])
    journey_me = auth_me(journey_owner_login["access_token"])
    check("owner" in journey_me["roles"], f"journey owner missing owner role: {journey_me}")
    journey_owner_id = journey_me["owner_id"]
    journey_owner_user_id = fetch_user_id(PHONES["journey_owner"])

    journey_group = api(
        "POST",
        "/api/groups",
        token=journey_owner_login["access_token"],
        json={
            "ownerId": journey_owner_id,
            "groupCode": f"JRN-{datetime.now().strftime('%H%M%S')}",
            "title": "Journey Public Group",
            "chitValue": 12000,
            "installmentAmount": 1200,
            "memberCount": 3,
            "cycleCount": 1,
            "cycleFrequency": "monthly",
            "visibility": "public",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10",
        },
        expected=201,
    ).json()
    check(journey_group["status"] == "active", f"journey group not active: {journey_group}")

    signup("Journey Member One", PHONES["journey_member_1"])
    signup("Journey Member Two", PHONES["journey_member_2"])
    member_one_login = login(PHONES["journey_member_1"])
    member_two_login = login(PHONES["journey_member_2"])

    request_member = api(
        "POST",
        f"/api/chits/{journey_group['id']}/request",
        token=member_one_login["access_token"],
        expected=200,
    ).json()
    request_member_two = api(
        "POST",
        f"/api/chits/{journey_group['id']}/request",
        token=member_two_login["access_token"],
        expected=200,
    ).json()
    approve_member = api(
        "POST",
        f"/api/chits/{journey_group['id']}/approve-member",
        token=journey_owner_login["access_token"],
        json={"membershipId": request_member["membershipId"]},
        expected=200,
    ).json()
    approve_member_two = api(
        "POST",
        f"/api/chits/{journey_group['id']}/approve-member",
        token=journey_owner_login["access_token"],
        json={"membershipId": request_member_two["membershipId"]},
        expected=200,
    ).json()
    check(approve_member["membershipStatus"] == "active", f"journey member one not active: {approve_member}")
    check(approve_member_two["membershipStatus"] == "active", f"journey member two not active: {approve_member_two}")

    member_one_subscriber_id = fetch_subscriber_id(PHONES["journey_member_1"])
    member_two_subscriber_id = fetch_subscriber_id(PHONES["journey_member_2"])
    member_one_membership = get_membership(journey_group["id"], member_one_subscriber_id)
    member_two_membership = get_membership(journey_group["id"], member_two_subscriber_id)
    add_extra_slot(member_one_membership["id"])
    session_id = create_open_auction_session(journey_group["id"], journey_owner_user_id)

    api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=member_one_login["access_token"],
        json={"membershipId": member_one_membership["id"], "bidAmount": 1000, "idempotencyKey": f"journey-1-{seed}"},
        expected=200,
    )
    api(
        "POST",
        f"/api/auctions/{session_id}/bids",
        token=member_two_login["access_token"],
        json={"membershipId": member_two_membership["id"], "bidAmount": 1100, "idempotencyKey": f"journey-2-{seed}"},
        expected=200,
    )
    finalized = api("POST", f"/api/auctions/{session_id}/finalize", token=journey_owner_login["access_token"], expected=200).json()
    check(finalized["status"] == "finalized", f"journey auction not finalized: {finalized}")

    installment = wait_until(
        lambda: get_first_installment(member_one_membership["id"]),
        description="journey installment creation",
    )
    payment = api(
        "POST",
        "/api/payments",
        token=journey_owner_login["access_token"],
        json={
            "ownerId": journey_owner_id,
            "subscriberId": member_one_subscriber_id,
            "membershipId": member_one_membership["id"],
            "installmentId": installment["id"],
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": installment["balance_amount"],
            "paymentDate": "2026-05-12",
            "referenceNo": f"JOURNEY-PAY-{seed}",
        },
        expected=201,
    ).json()
    balances = api(
        "GET",
        f"/api/payments/balances?subscriberId={member_one_subscriber_id}&groupId={journey_group['id']}",
        token=journey_owner_login["access_token"],
        expected=200,
    ).json()
    balance_item = balances[0] if isinstance(balances, list) else balances["items"][0]
    notifications_owner = wait_until(
        lambda: (
            lambda body: body if len(body["items"] if isinstance(body, dict) and "items" in body else body) > 0 else None
        )(
            api("GET", "/api/notifications", token=journey_owner_login["access_token"], expected=200).json()
        ),
        description="journey owner notifications",
    )
    notifications_member_two = wait_until(
        lambda: (
            lambda body: body if len(body["items"] if isinstance(body, dict) and "items" in body else body) > 0 else None
        )(
            api("GET", "/api/notifications", token=member_two_login["access_token"], expected=200).json()
        ),
        description="journey winner notifications",
    )
    notifications_owner_items = notifications_owner["items"] if isinstance(notifications_owner, dict) and "items" in notifications_owner else notifications_owner
    notifications_member_two_items = notifications_member_two["items"] if isinstance(notifications_member_two, dict) and "items" in notifications_member_two else notifications_member_two
    check(int(balance_item["outstandingAmount"]) == 0, f"journey balance not cleared: {balance_item}")
    check(len(notifications_owner_items) > 0, "journey owner notifications missing")
    check(len(notifications_member_two_items) > 0, "journey winner notifications missing")
    return {
        "ownerRequestId": owner_request["id"],
        "journeyRoles": journey_me["roles"],
        "journeyGroupId": journey_group["id"],
        "auctionSessionId": session_id,
        "winnerMembershipId": finalized["resultSummary"]["winnerMembershipId"],
        "paymentId": payment["id"],
        "finalOutstanding": balance_item["outstandingAmount"],
    }


for name, fn in [
    ("Batch 1 Auth", batch1),
    ("Batch 2 Role Resolution", batch2),
    ("Batch 3 Dashboard Permissions", batch3),
    ("Batch 4 Chit Activation", batch4),
    ("Batch 5 Membership Flow", batch5),
    ("Batch 6 Auction Finalize", batch6),
    ("Batch 7 Payment Ownership", batch7),
    ("Batch 8 External Chits", batch8),
    ("Batch 9 Infra Readiness", batch9),
    ("Batch 10 Full Journey", batch10),
]:
    run_batch(name, fn)

print(json.dumps({"seed": seed, "phones": PHONES, "results": results}, default=str, indent=2))
