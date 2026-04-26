from datetime import date, datetime, timezone
import json

from sqlalchemy import func, select
from fastapi import HTTPException

from app.core.security import CurrentUser
from app.models import AuditLog, ChitGroup, GroupMembership, Installment, Owner, Payout, Subscriber, User
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.modules.auctions.service import finalize_auction, finalize_auction_post_processing, place_bid
from app.modules.groups.service import close_group_collection
from app.modules.groups.join_service import join_group
from app.modules.payments.payout_service import settle_owner_payout
from app.modules.payments.service import record_payment
from app.core.audit import log_audit_event

import pytest

pytestmark = pytest.mark.usefixtures("app")


def _owner_current_user(db_session, phone: str = "9999999999") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    owner = db_session.scalar(select(Owner).where(Owner.user_id == user.id))
    assert owner is not None
    return CurrentUser(user=user, owner=owner, subscriber=None)


def _subscriber_current_user(db_session, phone: str = "8888888888") -> CurrentUser:
    user = db_session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    assert subscriber is not None
    return CurrentUser(user=user, owner=None, subscriber=subscriber)


def _seed_group(db_session, *, status: str = "active") -> ChitGroup:
    owner = db_session.scalar(select(Owner).order_by(Owner.id.asc()))
    assert owner is not None
    group = ChitGroup(
        owner_id=owner.id,
        group_code="AUDIT-001",
        title="Audit Group",
        chit_value=200000,
        installment_amount=10000,
        member_count=5,
        cycle_count=3,
        cycle_frequency="monthly",
        visibility="public",
        start_date=date(2026, 5, 1),
        first_auction_date=date(2026, 5, 10),
        current_cycle_no=1,
        bidding_enabled=True,
        status=status,
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def _seed_group_membership(db_session, group: ChitGroup, subscriber_id: int, member_no: int) -> GroupMembership:
    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=subscriber_id,
        member_no=member_no,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def _seed_open_session(db_session, group: ChitGroup) -> AuctionSession:
    session = AuctionSession(
        group_id=group.id,
        cycle_no=1,
        scheduled_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        actual_start_at=datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
        bidding_window_seconds=180,
        status="open",
        opened_by_user_id=1,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def test_log_audit_event_persists_serialized_metadata(db_session):
    owner = db_session.scalar(select(Owner).order_by(Owner.id.asc()))
    assert owner is not None
    audit_row = log_audit_event(
        db_session,
        action="group.created",
        entity_type="chit_group",
        entity_id="42",
        actor_user_id=owner.user_id,
        owner_id=owner.id,
        metadata={"groupId": 42, "status": "active"},
        before={"status": "draft"},
        after={"status": "active"},
    )

    persisted = db_session.scalar(select(AuditLog).where(AuditLog.id == audit_row.id))
    assert persisted is not None
    assert persisted.action == "group.created"
    assert persisted.entity_type == "chit_group"
    assert persisted.entity_id == "42"
    assert persisted.actor_user_id == owner.user_id
    assert persisted.owner_id == owner.id
    assert persisted.metadata_json == '{"groupId":42,"status":"active"}'
    assert persisted.before_json == '{"status":"draft"}'
    assert persisted.after_json == '{"status":"active"}'


def test_place_bid_records_audit_event(db_session, monkeypatch):
    group = _seed_group(db_session)
    membership = _seed_group_membership(db_session, group, subscriber_id=2, member_no=1)
    session = _seed_open_session(db_session, group)
    current_user = _subscriber_current_user(db_session)
    monkeypatch.setattr(
        "app.modules.auctions.service.utcnow",
        lambda: datetime(2026, 5, 10, 10, 1, tzinfo=timezone.utc),
    )

    result = place_bid(
        db_session,
        session.id,
        type("BidPayload", (), {"bidAmount": 12000, "idempotencyKey": "bid-001"})(),
        current_user,
    )

    audit_row = db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "auction_bid"))
    assert result["accepted"] is True
    assert audit_row is not None
    assert audit_row.action == "auction.bid.placed"
    assert audit_row.entity_id == str(result["bidId"])
    assert audit_row.actor_user_id == current_user.user.id
    assert audit_row.owner_id == group.owner_id
    assert json.loads(audit_row.metadata_json) == {
        "auctionSessionId": session.id,
        "bidAmount": 12000,
        "membershipId": membership.id,
    }
    assert json.loads(audit_row.before_json)["bidCount"] == 0
    assert json.loads(audit_row.after_json)["bidCount"] == 1


def test_record_payment_records_audit_event(db_session):
    group = _seed_group(db_session)
    subscriber = db_session.scalar(select(Subscriber).where(Subscriber.id == 2))
    assert subscriber is not None
    membership = _seed_group_membership(db_session, group, subscriber_id=subscriber.id, member_no=1)
    installment = Installment(
        group_id=group.id,
        membership_id=membership.id,
        cycle_no=1,
        due_date=date(2026, 5, 1),
        due_amount=5000,
        penalty_amount=0,
        paid_amount=0,
        balance_amount=5000,
        status="pending",
    )
    db_session.add(installment)
    db_session.commit()
    current_user = _owner_current_user(db_session)

    result = record_payment(
        db_session,
        type(
            "PaymentPayload",
            (),
                {
                    "ownerId": group.owner_id,
                    "paymentType": "installment",
                    "paymentMethod": "upi",
                    "amount": 5000,
                    "paymentDate": date(2026, 5, 5),
                    "referenceNo": "PAY-001",
                    "subscriberId": subscriber.id,
                    "membershipId": membership.id,
                    "installmentId": installment.id,
                },
        )(),
        current_user,
    )

    audit_row = db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "payment"))
    assert result["id"] > 0
    assert audit_row is not None
    assert audit_row.action == "payment.recorded"
    assert audit_row.entity_id == str(result["id"])
    assert audit_row.actor_user_id == current_user.user.id
    assert audit_row.owner_id == group.owner_id
    assert json.loads(audit_row.metadata_json) == {
        "amount": 5000,
        "groupId": group.id,
        "paymentMethod": "upi",
        "paymentType": "installment",
        "subscriberId": subscriber.id,
    }
    before_payload = json.loads(audit_row.before_json)
    after_payload = json.loads(audit_row.after_json)
    assert before_payload["installment"]["status"] == "pending"
    assert after_payload["installment"]["status"] == "paid"


def test_join_group_records_audit_event(db_session):
    group = _seed_group(db_session)
    current_user = _subscriber_current_user(db_session)

    result = join_group(db_session, group.id, {"subscriberId": current_user.subscriber.id, "memberNo": 3}, current_user)

    audit_row = db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "group_membership"))
    assert result["groupId"] == group.id
    assert audit_row is not None
    assert audit_row.action == "group.membership.joined"
    assert audit_row.entity_id == str(result["id"])
    assert audit_row.actor_user_id == current_user.user.id
    assert audit_row.owner_id == group.owner_id
    assert audit_row.metadata_json == f'{{"groupId":{group.id},"memberNo":3,"subscriberId":{current_user.subscriber.id}}}'


def test_close_group_collection_records_audit_event(db_session):
    group = _seed_group(db_session)
    current_user = _owner_current_user(db_session)

    result = close_group_collection(db_session, group.id, current_user)

    audit_row = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_type == "chit_group", AuditLog.entity_id == str(group.id))
        .order_by(AuditLog.id.desc())
    )
    assert result["id"] == group.id
    assert audit_row is not None
    assert audit_row.action == "group.collection_closed"
    assert audit_row.actor_user_id == current_user.user.id
    assert audit_row.owner_id == group.owner_id
    assert json.loads(audit_row.metadata_json) == {
        "groupId": group.id,
        "currentCycleNo": 1,
    }
    assert json.loads(audit_row.after_json) == {
        "collectionClosed": True,
        "currentMonthStatus": "COLLECTION_CLOSED",
    }


def test_finalize_auction_records_audit_event(db_session):
    group = _seed_group(db_session)
    membership = _seed_group_membership(db_session, group, subscriber_id=2, member_no=1)
    session = _seed_open_session(db_session, group)
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=2,
        idempotency_key="finalize-bid-001",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.commit()
    db_session.refresh(bid)
    result_row = AuctionResult(
        auction_session_id=session.id,
        group_id=group.id,
        cycle_no=session.cycle_no,
        winner_membership_id=membership.id,
        winning_bid_id=bid.id,
        winning_bid_amount=bid.bid_amount,
        dividend_pool_amount=0,
        dividend_per_member_amount=0,
        owner_commission_amount=0,
        winner_payout_amount=0,
        finalized_by_user_id=1,
        finalized_at=datetime(2026, 5, 10, 10, 5, tzinfo=timezone.utc),
    )
    db_session.add(result_row)
    db_session.commit()
    current_user = _owner_current_user(db_session)

    result = finalize_auction(db_session, session.id, current_user)

    audit_row = db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "auction_session"))
    assert result["status"] == "finalized"
    assert audit_row is not None
    assert audit_row.action == "auction.finalized"
    assert audit_row.entity_id == str(session.id)
    assert audit_row.actor_user_id == current_user.user.id
    assert audit_row.owner_id == group.owner_id
    assert audit_row.metadata_json == f'{{"auctionSessionId":{session.id},"cycleNo":1,"winningBidId":{bid.id}}}'
    assert json.loads(audit_row.before_json)["status"] == "finalizing"
    assert json.loads(audit_row.after_json)["status"] == "finalized"


def test_settle_owner_payout_records_audit_event(db_session):
    group = _seed_group(db_session)
    membership = _seed_group_membership(db_session, group, subscriber_id=2, member_no=1)
    session = _seed_open_session(db_session, group)
    bid = AuctionBid(
        auction_session_id=session.id,
        membership_id=membership.id,
        bidder_user_id=2,
        idempotency_key="payout-bid-001",
        bid_amount=12000,
        bid_discount_amount=0,
        placed_at=datetime(2026, 5, 10, 10, 1, tzinfo=timezone.utc),
        is_valid=True,
    )
    db_session.add(bid)
    db_session.commit()
    current_user = _owner_current_user(db_session)

    finalize_result = finalize_auction(db_session, session.id, current_user)
    queued_session_id = session.id
    finalize_auction_post_processing(db_session, session_id=queued_session_id)
    auction_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session.id))
    assert auction_result is not None
    payout = db_session.scalar(select(Payout).where(Payout.auction_result_id == auction_result.id))
    assert payout is not None
    assert finalize_result["status"] == "finalized"

    settled = settle_owner_payout(
        db_session,
        payout.id,
        current_user,
        payout_method="bank_transfer",
        payout_date=date(2026, 5, 12),
        reference_no="SETTLE-001",
    )

    payout_row = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.entity_type == "payout")
        .order_by(AuditLog.id.desc())
    )
    assert payout_row is not None
    assert payout_row.action == "payout.settled"
    assert payout_row.entity_id == str(payout.id)
    assert payout_row.actor_user_id == current_user.user.id
    assert payout_row.owner_id == group.owner_id
    assert settled["status"] == "paid"
    metadata = json.loads(payout_row.metadata_json)
    assert metadata["auctionResultId"] == auction_result.id
    assert metadata["groupId"] == group.id
    assert metadata["membershipId"] == membership.id
    assert metadata["subscriberId"] == payout.subscriber_id
    assert metadata["grossAmount"] == 200000.0
    assert metadata["deductionsAmount"] == float(payout.deductions_amount)
    assert metadata["netAmount"] == float(payout.net_amount)
    assert metadata["payoutMethod"] == "bank_transfer"
    assert metadata["payoutDate"] == "2026-05-12"
    assert metadata["referenceNo"] == "SETTLE-001"
    assert metadata["status"] == "paid"
    assert metadata["payoutId"] == payout.id
    assert isinstance(metadata["ledgerEntryId"], int)
    assert json.loads(payout_row.before_json)["status"] == "pending"
    assert json.loads(payout_row.after_json)["status"] == "paid"

    payout_count = db_session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.entity_type == "payout",
            AuditLog.entity_id == str(payout.id),
        )
    )
    assert payout_count == 1

    with pytest.raises(HTTPException):
        settle_owner_payout(db_session, payout.id, current_user)

    payout_count_after_retry = db_session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.entity_type == "payout",
            AuditLog.entity_id == str(payout.id),
        )
    )
    assert payout_count_after_retry == 1
