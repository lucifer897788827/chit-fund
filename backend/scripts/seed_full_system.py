from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    AuctionBid,
    AuctionResult,
    AuctionSession,
    ChitGroup,
    ExternalChit,
    ExternalChitEntry,
    GroupMembership,
    Installment,
    MembershipSlot,
    Owner,
    Payment,
    Payout,
    Subscriber,
    User,
)
from app.main import app


SEED_OWNER_PASSWORD = "Owner@123"
SEED_SUBSCRIBER_PASSWORD = "User@123"
SEED_OWNER_PHONES = ["7700000001", "7700000002", "7700000003"]
SEED_SUBSCRIBER_PHONES = [
    "7800000001",
    "7800000002",
    "7800000003",
    "7800000004",
    "7800000005",
    "7800000006",
    "7800000007",
    "7800000008",
    "7800000009",
    "7800000010",
]


@dataclass(frozen=True)
class OwnerSeed:
    phone: str
    full_name: str
    business_name: str
    city: str
    state: str


@dataclass(frozen=True)
class SubscriberSeed:
    phone: str
    full_name: str
    city: str
    state: str


@dataclass(frozen=True)
class GroupSeed:
    code: str
    title: str
    owner_phone: str
    member_phones: tuple[str, ...]
    chit_value: int
    installment_amount: int
    member_count: int
    cycle_count: int
    start_date: date
    first_auction_date: date
    current_cycle_no: int
    status: str


OWNERS = [
    OwnerSeed("7700000001", "Anand Kumar", "Anand Prime Chits", "Chennai", "Tamil Nadu"),
    OwnerSeed("7700000002", "Bhavani Raj", "Bhavani Growth Funds", "Coimbatore", "Tamil Nadu"),
    OwnerSeed("7700000003", "Dinesh Vel", "Dinesh Secure Circles", "Madurai", "Tamil Nadu"),
]

SUBSCRIBERS = [
    SubscriberSeed("7800000001", "Asha Raman", "Chennai", "Tamil Nadu"),
    SubscriberSeed("7800000002", "Bala K", "Chennai", "Tamil Nadu"),
    SubscriberSeed("7800000003", "Charan S", "Chennai", "Tamil Nadu"),
    SubscriberSeed("7800000004", "Deepa Nair", "Coimbatore", "Tamil Nadu"),
    SubscriberSeed("7800000005", "Eswar Prasad", "Coimbatore", "Tamil Nadu"),
    SubscriberSeed("7800000006", "Farah Ali", "Coimbatore", "Tamil Nadu"),
    SubscriberSeed("7800000007", "Gokul Raj", "Madurai", "Tamil Nadu"),
    SubscriberSeed("7800000008", "Harini S", "Madurai", "Tamil Nadu"),
    SubscriberSeed("7800000009", "Irfan Khan", "Trichy", "Tamil Nadu"),
    SubscriberSeed("7800000010", "Jaya Menon", "Salem", "Tamil Nadu"),
]

GROUPS = [
    GroupSeed(
        code="SEED-GRP-001",
        title="Chennai Prime Circle",
        owner_phone="7700000001",
        member_phones=("7800000001", "7800000002", "7800000003", "7800000004", "7800000005", "7800000006"),
        chit_value=300000,
        installment_amount=15000,
        member_count=6,
        cycle_count=10,
        start_date=date(2026, 1, 1),
        first_auction_date=date(2026, 1, 20),
        current_cycle_no=3,
        status="active",
    ),
    GroupSeed(
        code="SEED-GRP-002",
        title="Coimbatore Growth Circle",
        owner_phone="7700000002",
        member_phones=("7800000004", "7800000005", "7800000006", "7800000007", "7800000008", "7800000009"),
        chit_value=240000,
        installment_amount=12000,
        member_count=6,
        cycle_count=10,
        start_date=date(2026, 2, 1),
        first_auction_date=date(2026, 2, 18),
        current_cycle_no=3,
        status="active",
    ),
    GroupSeed(
        code="SEED-GRP-003",
        title="Madurai Secure Circle",
        owner_phone="7700000003",
        member_phones=("7800000002", "7800000007", "7800000008", "7800000009", "7800000010"),
        chit_value=200000,
        installment_amount=10000,
        member_count=5,
        cycle_count=8,
        start_date=date(2025, 11, 1),
        first_auction_date=date(2025, 11, 18),
        current_cycle_no=4,
        status="completed",
    ),
]

WINNER_PLAN = {
    "SEED-GRP-001": {1: "7800000002", 2: "7800000005"},
    "SEED-GRP-002": {1: "7800000004", 2: "7800000008"},
    "SEED-GRP-003": {1: "7800000007", 2: "7800000010"},
}

BID_PLAN = {
    "SEED-GRP-001": {1: 18000, 2: 22000},
    "SEED-GRP-002": {1: 12000, 2: 15000},
    "SEED-GRP-003": {1: 10000, 2: 13000},
}

PAYMENT_PATTERN = {
    "7800000001": ("paid", "paid", "paid"),
    "7800000002": ("paid", "paid", "pending"),
    "7800000003": ("partial", "pending", "pending"),
    "7800000004": ("paid", "paid", "paid"),
    "7800000005": ("paid", "pending", "pending"),
    "7800000006": ("paid", "paid", "pending"),
    "7800000007": ("paid", "partial", "pending"),
    "7800000008": ("paid", "paid", "paid"),
    "7800000009": ("partial", "pending", "pending"),
    "7800000010": ("paid", "pending", "pending"),
}


def _email_for(prefix: str, phone: str) -> str:
    return f"{prefix}.{phone}@example.com"


def _admin_user(db) -> User:
    admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id.asc()).limit(1))
    if admin is None:
        raise RuntimeError("Admin account not found; seeding aborted.")
    return admin


def _owner_by_phone(db, phone: str) -> Owner:
    owner = db.scalar(
        select(Owner).join(User, User.id == Owner.user_id).where(User.phone == phone)
    )
    if owner is None:
        raise RuntimeError(f"Owner with phone {phone} not found")
    return owner


def _subscriber_by_phone(db, phone: str) -> Subscriber:
    subscriber = db.scalar(
        select(Subscriber).join(User, User.id == Subscriber.user_id).where(User.phone == phone)
    )
    if subscriber is None:
        raise RuntimeError(f"Subscriber with phone {phone} not found")
    return subscriber


def _user_by_phone(db, phone: str) -> User:
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        raise RuntimeError(f"User with phone {phone} not found")
    return user


def batch_1_users() -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id)).where(User.phone.in_(SEED_OWNER_PHONES + SEED_SUBSCRIBER_PHONES))):
            print("Batch 1 — USERS: seed users already present, skipping creation")
            print(
                {
                    "owners": db.scalar(select(func.count(Owner.id))) or 0,
                    "subscribers": db.scalar(select(func.count(Subscriber.id))) or 0,
                }
            )
            return

        for index, owner_seed in enumerate(OWNERS):
            user = User(
                email=_email_for("seed.owner", owner_seed.phone),
                phone=owner_seed.phone,
                password_hash=hash_password(SEED_OWNER_PASSWORD),
                role="chit_owner",
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(
                Owner(
                    user_id=user.id,
                    display_name=owner_seed.full_name,
                    business_name=owner_seed.business_name,
                    city=owner_seed.city,
                    state=owner_seed.state,
                    status="active",
                )
            )

        for index, subscriber_seed in enumerate(SUBSCRIBERS):
            owner = _owner_by_phone(db, OWNERS[index % len(OWNERS)].phone)
            user = User(
                email=_email_for("seed.subscriber", subscriber_seed.phone),
                phone=subscriber_seed.phone,
                password_hash=hash_password(SEED_SUBSCRIBER_PASSWORD),
                role="subscriber",
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(
                Subscriber(
                    user_id=user.id,
                    owner_id=owner.id,
                    full_name=subscriber_seed.full_name,
                    phone=subscriber_seed.phone,
                    email=user.email,
                    address_text=f"{subscriber_seed.city}, {subscriber_seed.state}",
                    status="active",
                    auto_created=False,
                )
            )

        db.commit()
        print("Batch 1 — USERS: created 3 owners and 10 subscribers")
        print(
            {
                "seed_owner_users": db.scalar(select(func.count(User.id)).where(User.phone.in_(SEED_OWNER_PHONES))) or 0,
                "seed_subscriber_users": db.scalar(select(func.count(User.id)).where(User.phone.in_(SEED_SUBSCRIBER_PHONES))) or 0,
            }
        )


def _ensure_group_memberships_and_installments(db, group_seed: GroupSeed) -> ChitGroup:
    existing_group = db.scalar(select(ChitGroup).where(ChitGroup.group_code == group_seed.code))
    if existing_group is not None:
        return existing_group

    owner = _owner_by_phone(db, group_seed.owner_phone)
    group = ChitGroup(
        owner_id=owner.id,
        group_code=group_seed.code,
        title=group_seed.title,
        chit_value=group_seed.chit_value,
        installment_amount=group_seed.installment_amount,
        member_count=group_seed.member_count,
        cycle_count=group_seed.cycle_count,
        cycle_frequency="monthly",
        start_date=group_seed.start_date,
        first_auction_date=group_seed.first_auction_date,
        current_cycle_no=group_seed.current_cycle_no,
        bidding_enabled=True,
        status=group_seed.status,
    )
    db.add(group)
    db.flush()

    for member_no, phone in enumerate(group_seed.member_phones, start=1):
        subscriber = _subscriber_by_phone(db, phone)
        subscriber_user = _user_by_phone(db, phone)
        membership = GroupMembership(
            group_id=group.id,
            subscriber_id=subscriber.id,
            member_no=member_no,
            membership_status="completed" if group_seed.status == "completed" else "active",
            prized_status="unprized",
            can_bid=True,
        )
        db.add(membership)
        db.flush()
        db.add(
            MembershipSlot(
                user_id=subscriber_user.id,
                group_id=group.id,
                slot_number=member_no,
                has_won=False,
            )
        )
        for cycle_no in range(1, 4):
            due_date = group_seed.start_date + timedelta(days=30 * (cycle_no - 1))
            db.add(
                Installment(
                    group_id=group.id,
                    membership_id=membership.id,
                    cycle_no=cycle_no,
                    due_date=due_date,
                    due_amount=group_seed.installment_amount,
                    penalty_amount=0,
                    paid_amount=0,
                    balance_amount=group_seed.installment_amount,
                    status="pending",
                )
            )

    return group


def batch_2_groups() -> None:
    with SessionLocal() as db:
        created_codes = []
        for group_seed in GROUPS:
            before = db.scalar(select(ChitGroup.id).where(ChitGroup.group_code == group_seed.code))
            group = _ensure_group_memberships_and_installments(db, group_seed)
            if before is None:
                created_codes.append(group.group_code)
        db.commit()
        print(f"Batch 2 — GROUPS: created/verified {len(GROUPS)} groups")
        print(
            {
                "created_groups": created_codes,
                "groups": db.scalar(select(func.count(ChitGroup.id)).where(ChitGroup.group_code.in_([group.code for group in GROUPS]))) or 0,
                "memberships": db.scalar(
                    select(func.count(GroupMembership.id)).where(
                        GroupMembership.group_id.in_(select(ChitGroup.id).where(ChitGroup.group_code.in_([group.code for group in GROUPS])))
                    )
                ) or 0,
            }
        )


def batch_3_auctions() -> None:
    with SessionLocal() as db:
        admin = _admin_user(db)
        sessions_created = 0
        results_created = 0
        payouts_created = 0

        for group_seed in GROUPS:
            group = db.scalar(select(ChitGroup).where(ChitGroup.group_code == group_seed.code))
            memberships = db.scalars(
                select(GroupMembership).where(GroupMembership.group_id == group.id).order_by(GroupMembership.member_no.asc())
            ).all()
            membership_by_phone = {
                db.scalar(select(User.phone).join(Subscriber, Subscriber.user_id == User.id).where(Subscriber.id == membership.subscriber_id)): membership
                for membership in memberships
            }
            for cycle_no, winner_phone in WINNER_PLAN[group_seed.code].items():
                scheduled_at = datetime.combine(
                    group_seed.first_auction_date + timedelta(days=30 * (cycle_no - 1)),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ).replace(hour=12)
                session = db.scalar(
                    select(AuctionSession).where(AuctionSession.group_id == group.id, AuctionSession.cycle_no == cycle_no)
                )
                if session is None:
                    session = AuctionSession(
                        group_id=group.id,
                        cycle_no=cycle_no,
                        scheduled_start_at=scheduled_at,
                        actual_start_at=scheduled_at,
                        actual_end_at=scheduled_at + timedelta(minutes=15),
                        bidding_window_seconds=180,
                        status="closed",
                        opened_by_user_id=admin.id,
                        closed_by_user_id=admin.id,
                    )
                    db.add(session)
                    db.flush()
                    sessions_created += 1

                winner_membership = membership_by_phone[winner_phone]
                bid_memberships = [membership_by_phone[winner_phone], memberships[0], memberships[-1]]
                bid_memberships = list(dict.fromkeys(member.id for member in bid_memberships))
                bid_objects = []
                for offset, membership_id in enumerate(bid_memberships, start=1):
                    membership = next(item for item in memberships if item.id == membership_id)
                    subscriber = db.get(Subscriber, membership.subscriber_id)
                    bidder_user = db.get(User, subscriber.user_id)
                    bid_amount = max(BID_PLAN[group_seed.code][cycle_no] - (offset - 1) * 1000, 1000)
                    bid = db.scalar(
                        select(AuctionBid).where(
                            AuctionBid.auction_session_id == session.id,
                            AuctionBid.membership_id == membership.id,
                            AuctionBid.idempotency_key == f"{group_seed.code}-cycle-{cycle_no}-bid-{offset}",
                        )
                    )
                    if bid is None:
                        bid = AuctionBid(
                            auction_session_id=session.id,
                            membership_id=membership.id,
                            bidder_user_id=bidder_user.id,
                            idempotency_key=f"{group_seed.code}-cycle-{cycle_no}-bid-{offset}",
                            bid_amount=bid_amount,
                            bid_discount_amount=bid_amount,
                            placed_at=scheduled_at + timedelta(minutes=offset * 2),
                            is_valid=True,
                        )
                        db.add(bid)
                        db.flush()
                    bid_objects.append(bid)

                winning_bid = bid_objects[0]
                result = db.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
                winner_payout_amount = max(group.installment_amount - BID_PLAN[group_seed.code][cycle_no] // 2, group.installment_amount // 2)
                if result is None:
                    result = AuctionResult(
                        auction_session_id=session.id,
                        group_id=group.id,
                        cycle_no=cycle_no,
                        winner_membership_id=winner_membership.id,
                        winning_bid_id=winning_bid.id,
                        winning_bid_amount=BID_PLAN[group_seed.code][cycle_no],
                        dividend_pool_amount=group.installment_amount,
                        dividend_per_member_amount=max(group.installment_amount // max(group.member_count, 1), 1),
                        owner_commission_amount=max(group.installment_amount // 10, 500),
                        winner_payout_amount=winner_payout_amount,
                        finalized_by_user_id=admin.id,
                        finalized_at=scheduled_at + timedelta(minutes=20),
                    )
                    db.add(result)
                    db.flush()
                    results_created += 1

                payout = db.scalar(select(Payout).where(Payout.auction_result_id == result.id))
                if payout is None:
                    subscriber = db.get(Subscriber, winner_membership.subscriber_id)
                    payout = Payout(
                        owner_id=group.owner_id,
                        auction_result_id=result.id,
                        subscriber_id=subscriber.id,
                        membership_id=winner_membership.id,
                        gross_amount=group.installment_amount,
                        deductions_amount=max(BID_PLAN[group_seed.code][cycle_no] // 3, 1000),
                        net_amount=winner_payout_amount,
                        payout_method="bank_transfer",
                        payout_date=(scheduled_at + timedelta(days=1)).date(),
                        status="paid",
                        payout_expanded=True,
                        paid_at=scheduled_at + timedelta(days=1),
                    )
                    db.add(payout)
                    payouts_created += 1

                winner_membership.prized_status = "prized"
                winner_membership.prized_cycle_no = cycle_no
                winner_membership.can_bid = False
                winner_slot = db.scalar(
                    select(MembershipSlot).where(
                        MembershipSlot.group_id == group.id,
                        MembershipSlot.user_id == db.get(User, db.get(Subscriber, winner_membership.subscriber_id).user_id).id,
                    )
                )
                if winner_slot is not None:
                    winner_slot.has_won = True

        db.commit()
        print("Batch 3 — AUCTIONS: created realistic closed auction rounds with winners and payouts")
        print(
            {
                "sessions_created": sessions_created,
                "results_created": results_created,
                "payouts_created": payouts_created,
            }
        )


def _installment_payment_status(phone: str, cycle_no: int) -> str:
    return PAYMENT_PATTERN[phone][cycle_no - 1]


def batch_4_payments() -> None:
    with SessionLocal() as db:
        admin = _admin_user(db)
        payments_created = 0

        groups = db.scalars(select(ChitGroup).where(ChitGroup.group_code.in_([group.code for group in GROUPS]))).all()
        for group in groups:
            memberships = db.scalars(select(GroupMembership).where(GroupMembership.group_id == group.id)).all()
            for membership in memberships:
                subscriber = db.get(Subscriber, membership.subscriber_id)
                user = db.get(User, subscriber.user_id)
                installments = db.scalars(
                    select(Installment).where(Installment.membership_id == membership.id).order_by(Installment.cycle_no.asc())
                ).all()
                for installment in installments:
                    status_name = _installment_payment_status(user.phone, installment.cycle_no)
                    if status_name == "paid":
                        paid_amount = installment.due_amount
                        installment.status = "paid"
                    elif status_name == "partial":
                        paid_amount = installment.due_amount // 2
                        installment.status = "partial"
                    else:
                        paid_amount = 0
                        installment.status = "pending"
                    installment.paid_amount = paid_amount
                    installment.balance_amount = max(installment.due_amount - paid_amount, 0)
                    if paid_amount > 0:
                        installment.last_paid_at = datetime.combine(
                            installment.due_date, datetime.min.time(), tzinfo=timezone.utc
                        )
                        payment = db.scalar(
                            select(Payment).where(Payment.installment_id == installment.id)
                        )
                        if payment is None:
                            payment = Payment(
                                owner_id=group.owner_id,
                                subscriber_id=subscriber.id,
                                membership_id=membership.id,
                                installment_id=installment.id,
                                payment_type="installment",
                                payment_method="upi" if installment.cycle_no % 2 else "cash",
                                amount=paid_amount,
                                payment_date=installment.due_date,
                                recorded_by_user_id=admin.id,
                                notes=f"Seed payment for {group.group_code} cycle {installment.cycle_no}",
                                status="paid",
                            )
                            db.add(payment)
                            payments_created += 1

        db.commit()
        defaulters = db.scalar(
            select(func.count(func.distinct(Subscriber.id)))
            .join(GroupMembership, GroupMembership.subscriber_id == Subscriber.id)
            .join(Installment, Installment.membership_id == GroupMembership.id)
            .where(Installment.balance_amount > 0)
        ) or 0
        print("Batch 4 — PAYMENTS: created paid and defaulter patterns")
        print(
            {
                "payments_created": payments_created,
                "payments_total": db.scalar(select(func.count(Payment.id))) or 0,
                "defaulters_detected": int(defaulters),
            }
        )


def batch_5_external_chits() -> None:
    with SessionLocal() as db:
        created = 0
        for idx, phone in enumerate(("7800000001", "7800000003", "7800000005"), start=1):
            subscriber = _subscriber_by_phone(db, phone)
            user = _user_by_phone(db, phone)
            title = f"Seed External Chit {idx}"
            external = db.scalar(
                select(ExternalChit).where(
                    ExternalChit.subscriber_id == subscriber.id,
                    ExternalChit.title == title,
                )
            )
            if external is None:
                external = ExternalChit(
                    subscriber_id=subscriber.id,
                    user_id=user.id,
                    title=title,
                    name=title,
                    organizer_name=f"Organizer {idx}",
                    chit_value=120000 + idx * 10000,
                    installment_amount=6000 + idx * 500,
                    monthly_installment=6000 + idx * 500,
                    total_members=20,
                    total_months=20,
                    user_slots=1,
                    first_month_organizer=idx == 1,
                    cycle_frequency="monthly",
                    start_date=date(2025, 10, 1) + timedelta(days=30 * idx),
                    end_date=date(2027, 4, 1) + timedelta(days=30 * idx),
                    status="active" if idx < 3 else "completed",
                    notes="Seeded external chit for testing",
                )
                db.add(external)
                db.flush()
                for month_number in range(1, 4):
                    db.add(
                        ExternalChitEntry(
                            external_chit_id=external.id,
                            month_number=month_number,
                            bid_amount=4000 + month_number * 500,
                            winner_type="member",
                            winner_name=f"Member {month_number}",
                            share_per_slot=500 + month_number * 50,
                            my_share=500 + month_number * 50,
                            my_payable=external.installment_amount - (500 + month_number * 50),
                            my_payout=2000 if month_number == 2 else 0,
                            entry_type="monthly",
                            entry_date=external.start_date + timedelta(days=30 * (month_number - 1)),
                            amount=external.installment_amount,
                            description=f"Seed month {month_number}",
                        )
                    )
                created += 1
        db.commit()
        print("Batch 5 — EXTERNAL CHITS: created external chits and entries")
        print(
            {
                "external_chits_total": db.scalar(select(func.count(ExternalChit.id))) or 0,
                "created_now": created,
            }
        )


def batch_6_validation() -> None:
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"phone": "7584928285", "password": "temp123"})
        assert login.status_code == 200, login.text
        admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        summary = client.get("/api/admin/insights/summary", headers=admin_headers)
        defaulters = client.get("/api/admin/insights/defaulters", headers=admin_headers)
        groups = client.get("/api/admin/groups", headers=admin_headers)
        assert summary.status_code == 200, summary.text
        assert defaulters.status_code == 200, defaulters.text
        assert groups.status_code == 200, groups.text
        groups_body = groups.json()
        assert groups_body, "Expected seeded groups in admin list"

        first_group_id = groups_body[0]["id"]
        group_detail = client.get(f"/api/admin/groups/{first_group_id}", headers=admin_headers)
        assert group_detail.status_code == 200, group_detail.text
        group_detail_body = group_detail.json()
        assert group_detail_body["members"], "Expected group members"
        assert group_detail_body["financialSummary"]["totalCollected"] > 0, "Expected collected payments"

        subscriber_login = client.post("/api/auth/login", json={"phone": "7800000002", "password": SEED_SUBSCRIBER_PASSWORD})
        assert subscriber_login.status_code == 200, subscriber_login.text
        subscriber_headers = {"Authorization": f"Bearer {subscriber_login.json()['access_token']}"}
        dashboard = client.get("/api/users/me/dashboard", headers=subscriber_headers)
        financials = client.get("/api/users/me/financial-summary", headers=subscriber_headers)
        assert dashboard.status_code == 200, dashboard.text
        assert financials.status_code == 200, financials.text
        dashboard_body = dashboard.json()
        financials_body = financials.json()
        assert dashboard_body["financial_summary"]["netPosition"] != 0, "Expected visible profit/loss signal"

        print("Batch 6 — VALIDATION: API checks passed")
        print(
            {
                "admin_summary": summary.json(),
                "defaulters_count": len(defaulters.json()),
                "groups_count": len(groups_body),
                "group_detail_members": len(group_detail_body["members"]),
                "subscriber_net_position": financials_body["netPosition"],
            }
        )


def main() -> None:
    print("Starting full system seed...")
    batch_1_users()
    batch_2_groups()
    batch_3_auctions()
    batch_4_payments()
    batch_5_external_chits()
    batch_6_validation()
    print("Seed data created successfully.")


if __name__ == "__main__":
    main()
