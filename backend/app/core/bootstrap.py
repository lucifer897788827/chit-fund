from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core import database
from app.core.security import hash_password
from app.models import AuctionSession, ChitGroup, ExternalChit, GroupMembership, Installment, Owner, Subscriber, User


def bootstrap_database() -> None:
    database.Base.metadata.create_all(bind=database.engine)

    with database.SessionLocal() as db:
        existing_user = db.scalar(select(User.id).limit(1))
        if existing_user is not None:
            return

        owner_user = User(
            email="owner@example.com",
            phone="9999999999",
            password_hash=hash_password("secret123"),
            role="chit_owner",
            is_active=True,
        )
        subscriber_user = User(
            email="subscriber@example.com",
            phone="8888888888",
            password_hash=hash_password("pass123"),
            role="subscriber",
            is_active=True,
        )
        db.add_all([owner_user, subscriber_user])
        db.flush()

        owner = Owner(
            user_id=owner_user.id,
            display_name="Owner One",
            business_name="Owner One Chits",
            city="Chennai",
            state="Tamil Nadu",
            status="active",
        )
        db.add(owner)
        db.flush()

        owner_profile = Subscriber(
            user_id=owner_user.id,
            owner_id=owner.id,
            full_name="Owner One",
            phone=owner_user.phone,
            email=owner_user.email,
            status="active",
        )
        subscriber_profile = Subscriber(
            user_id=subscriber_user.id,
            owner_id=owner.id,
            full_name="Subscriber One",
            phone=subscriber_user.phone,
            email=subscriber_user.email,
            status="active",
        )
        db.add_all([owner_profile, subscriber_profile])
        db.flush()

        group = ChitGroup(
            owner_id=owner.id,
            group_code="CHIT-001",
            title="April Gold Circle",
            chit_value=300000,
            installment_amount=15000,
            member_count=20,
            cycle_count=20,
            cycle_frequency="monthly",
            start_date=date(2026, 4, 1),
            first_auction_date=date(2026, 4, 20),
            current_cycle_no=1,
            bidding_enabled=True,
            status="active",
        )
        db.add(group)
        db.flush()

        memberships = [
            GroupMembership(
                group_id=group.id,
                subscriber_id=owner_profile.id,
                member_no=1,
                membership_status="active",
                prized_status="unprized",
                can_bid=True,
            ),
            GroupMembership(
                group_id=group.id,
                subscriber_id=subscriber_profile.id,
                member_no=2,
                membership_status="active",
                prized_status="unprized",
                can_bid=True,
            ),
        ]
        db.add_all(memberships)
        db.flush()

        for membership in memberships:
            db.add(
                Installment(
                    group_id=group.id,
                    membership_id=membership.id,
                    cycle_no=1,
                    due_date=group.start_date,
                    due_amount=group.installment_amount,
                    penalty_amount=0,
                    paid_amount=0,
                    balance_amount=group.installment_amount,
                    status="pending",
                )
            )

        db.add(
            AuctionSession(
                group_id=group.id,
                cycle_no=1,
                scheduled_start_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                actual_start_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                bidding_window_seconds=180,
                status="open",
                opened_by_user_id=owner_user.id,
            )
        )
        db.add(
            ExternalChit(
                subscriber_id=subscriber_profile.id,
                title="Neighbourhood Savings Pot",
                organizer_name="Lakshmi",
                chit_value=120000,
                installment_amount=6000,
                cycle_frequency="monthly",
                start_date=date(2026, 3, 1),
                status="active",
            )
        )
        db.commit()
