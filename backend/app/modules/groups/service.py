from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auction import AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment


def create_group(db: Session, payload):
    group = ChitGroup(
        owner_id=payload.ownerId,
        group_code=payload.groupCode,
        title=payload.title,
        chit_value=payload.chitValue,
        installment_amount=payload.installmentAmount,
        member_count=payload.memberCount,
        cycle_count=payload.cycleCount,
        cycle_frequency=payload.cycleFrequency,
        start_date=payload.startDate,
        first_auction_date=payload.firstAuctionDate,
        current_cycle_no=1,
        bidding_enabled=True,
        status="draft",
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return {
        "id": group.id,
        "ownerId": group.owner_id,
        "groupCode": group.group_code,
        "title": group.title,
        "chitValue": float(group.chit_value),
        "installmentAmount": float(group.installment_amount),
        "memberCount": group.member_count,
        "cycleCount": group.cycle_count,
        "cycleFrequency": group.cycle_frequency,
        "startDate": group.start_date,
        "firstAuctionDate": group.first_auction_date,
        "currentCycleNo": group.current_cycle_no,
        "biddingEnabled": group.bidding_enabled,
        "status": group.status,
    }


def list_groups(db: Session, owner_id: int):
    groups = db.scalars(
        select(ChitGroup).where(ChitGroup.owner_id == owner_id).order_by(ChitGroup.id.asc())
    ).all()
    return [
        {
            "id": group.id,
            "ownerId": group.owner_id,
            "groupCode": group.group_code,
            "title": group.title,
            "chitValue": float(group.chit_value),
            "installmentAmount": float(group.installment_amount),
            "memberCount": group.member_count,
            "cycleCount": group.cycle_count,
            "cycleFrequency": group.cycle_frequency,
            "startDate": group.start_date,
            "firstAuctionDate": group.first_auction_date,
            "currentCycleNo": group.current_cycle_no,
            "biddingEnabled": group.bidding_enabled,
            "status": group.status,
        }
        for group in groups
    ]


def _add_months(base_date: date, months_to_add: int) -> date:
    month_index = base_date.month - 1 + months_to_add
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _calculate_due_date(start_date: date, cycle_frequency: str, cycle_no: int) -> date:
    if cycle_frequency == "weekly":
        return start_date + timedelta(days=(cycle_no - 1) * 7)
    return _add_months(start_date, cycle_no - 1)


def create_membership(db: Session, group_id: int, payload):
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    membership = GroupMembership(
        group_id=group.id,
        subscriber_id=payload.subscriberId,
        member_no=payload.memberNo,
        membership_status="active",
        prized_status="unprized",
        can_bid=True,
    )
    db.add(membership)
    db.flush()

    for cycle_no in range(1, group.cycle_count + 1):
        due_date = _calculate_due_date(group.start_date, group.cycle_frequency, cycle_no)
        installment = Installment(
            group_id=group.id,
            membership_id=membership.id,
            cycle_no=cycle_no,
            due_date=due_date,
            due_amount=group.installment_amount,
            penalty_amount=0,
            paid_amount=0,
            balance_amount=group.installment_amount,
            status="pending",
        )
        db.add(installment)

    db.commit()
    db.refresh(membership)

    return {
        "id": membership.id,
        "groupId": membership.group_id,
        "subscriberId": membership.subscriber_id,
        "memberNo": membership.member_no,
        "membershipStatus": membership.membership_status,
        "prizedStatus": membership.prized_status,
        "canBid": membership.can_bid,
    }


def create_auction_session(db: Session, group_id: int, payload):
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    scheduled_start = datetime.combine(
        group.first_auction_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    session = AuctionSession(
        group_id=group.id,
        cycle_no=payload.cycleNo,
        scheduled_start_at=scheduled_start,
        actual_start_at=scheduled_start,
        bidding_window_seconds=payload.biddingWindowSeconds,
        status="open",
        opened_by_user_id=1,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "groupId": session.group_id,
        "cycleNo": session.cycle_no,
        "status": session.status,
        "biddingWindowSeconds": session.bidding_window_seconds,
    }
