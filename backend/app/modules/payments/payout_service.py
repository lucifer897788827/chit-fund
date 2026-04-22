from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.money import money_int
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner
from app.core.time import utcnow
from app.models.auction import AuctionResult
from app.models.chit import ChitGroup, GroupMembership
from app.models.money import LedgerEntry, Payout
from app.models.user import Subscriber
from app.modules.notifications.service import (
    dispatch_staged_notifications,
    notify_payout_created,
    notify_payout_settled,
)
from app.modules.payments.auction_payout_engine import build_membership_payables_from_result
from app.modules.payments.installment_service import (
    apply_membership_payables_for_cycle,
    build_membership_dues_snapshot_map,
)
from app.modules.payments.validation import (
    is_settled_payout_status,
    normalize_payout_status,
    payout_status_filter_values,
)


def _build_payout_description(db: Session, payout: Payout, result: AuctionResult) -> str:
    membership = db.get(GroupMembership, payout.membership_id)
    subscriber = db.get(Subscriber, payout.subscriber_id)
    group = db.get(ChitGroup, result.group_id)

    parts: list[str] = ["Auction payout"]
    if subscriber is not None:
        parts.append(f"for {subscriber.full_name}")
    if membership is not None:
        parts.append(f"member {membership.member_no}")
    if result.cycle_no is not None:
        parts.append(f"cycle {result.cycle_no}")
    if group is not None:
        parts.append(f"in {group.title}")
    return " ".join(parts)[:255]


def _upsert_payout_ledger_entry(db: Session, payout: Payout, result: AuctionResult) -> LedgerEntry:
    entry = db.scalar(
        select(LedgerEntry).where(
            LedgerEntry.source_table == "payouts",
            LedgerEntry.source_id == payout.id,
        )
    )
    payout_amount = money_int(payout.net_amount)
    entry_date = payout.payout_date or (result.finalized_at or utcnow()).date()
    description = _build_payout_description(db, payout, result)

    if entry is None:
        entry = LedgerEntry(
            owner_id=payout.owner_id,
            entry_date=entry_date,
            entry_type="payout",
            source_table="payouts",
            source_id=payout.id,
            subscriber_id=payout.subscriber_id,
            group_id=result.group_id,
            debit_amount=0,
            credit_amount=payout_amount,
            description=description,
        )
        db.add(entry)
    else:
        entry.owner_id = payout.owner_id
        entry.entry_date = entry_date
        entry.entry_type = "payout"
        entry.subscriber_id = payout.subscriber_id
        entry.group_id = result.group_id
        entry.debit_amount = 0
        entry.credit_amount = payout_amount
        entry.description = description

    db.flush()
    return entry


def ensure_auction_payout(db: Session, *, result: AuctionResult) -> tuple[Payout, LedgerEntry]:
    group = db.get(ChitGroup, result.group_id)
    if group is None:
        raise ValueError("Chit group not found for payout creation")

    membership = db.get(GroupMembership, result.winner_membership_id)
    if membership is None:
        raise ValueError("Winner membership not found for payout creation")

    payout = db.scalar(select(Payout).where(Payout.auction_result_id == result.id))
    payout_date = (result.finalized_at or utcnow()).date()
    gross_amount = money_int(group.chit_value)
    net_amount = money_int(result.winner_payout_amount)
    deductions_amount = gross_amount - net_amount
    is_new_payout = payout is None

    if payout is not None:
        normalized_status = normalize_payout_status(payout.status)
        if is_settled_payout_status(normalized_status):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Payout already settled",
            )
        if payout.owner_id != group.owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot settle another owner's payout",
            )

    if payout is None:
        payout = Payout(
            owner_id=group.owner_id,
            auction_result_id=result.id,
            subscriber_id=membership.subscriber_id,
            membership_id=membership.id,
            gross_amount=gross_amount,
            deductions_amount=deductions_amount,
            net_amount=net_amount,
            payout_method="auction_settlement",
            payout_date=payout_date,
            status=normalize_payout_status(None),
        )
        db.add(payout)
        db.flush()
    else:
        payout.owner_id = group.owner_id
        payout.subscriber_id = membership.subscriber_id
        payout.membership_id = membership.id
        payout.gross_amount = gross_amount
        payout.deductions_amount = deductions_amount
        payout.net_amount = net_amount
        payout.payout_method = "auction_settlement"
        payout.payout_date = payout.payout_date or payout_date
        payout.status = normalized_status

    membership_payables = build_membership_payables_from_result(db, result=result, group=group)
    apply_membership_payables_for_cycle(
        db,
        group=group,
        cycle_no=result.cycle_no,
        membership_payables=membership_payables,
    )

    ledger_entry = _upsert_payout_ledger_entry(db, payout, result)
    notify_payout_created(db, payout=payout)
    return payout, ledger_entry


def _serialize_payout(
    db: Session,
    payout: Payout,
    *,
    result: AuctionResult | None = None,
    dues_snapshot=None,
) -> dict:
    payout_result = result or db.get(AuctionResult, payout.auction_result_id)
    membership = db.get(GroupMembership, payout.membership_id)
    subscriber = db.get(Subscriber, payout.subscriber_id)
    group = db.get(ChitGroup, payout_result.group_id) if payout_result is not None else None

    payload = {
        "id": payout.id,
        "ownerId": payout.owner_id,
        "auctionResultId": payout.auction_result_id,
        "subscriberId": payout.subscriber_id,
        "membershipId": payout.membership_id,
        "groupId": payout_result.group_id if payout_result is not None else None,
        "groupCode": group.group_code if group is not None else None,
        "groupTitle": group.title if group is not None else None,
        "cycleNo": payout_result.cycle_no if payout_result is not None else None,
        "subscriberName": subscriber.full_name if subscriber is not None else None,
        "memberNo": membership.member_no if membership is not None else None,
        "grossAmount": money_int(payout.gross_amount),
        "deductionsAmount": money_int(payout.deductions_amount),
        "netAmount": money_int(payout.net_amount),
        "payoutMethod": payout.payout_method,
        "payoutDate": payout.payout_date,
        "referenceNo": payout.reference_no,
        "status": payout.status,
        "createdAt": payout.created_at,
        "updatedAt": payout.updated_at,
    }
    if dues_snapshot is not None:
        payload.update(dues_snapshot.as_dict())
    return payload


def list_owner_payouts(
    db: Session,
    current_user: CurrentUser,
    *,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    status: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)

    statement = (
        select(Payout)
        .join(AuctionResult, AuctionResult.id == Payout.auction_result_id)
        .where(Payout.owner_id == owner.id)
    )

    if subscriber_id is not None:
        statement = statement.where(Payout.subscriber_id == subscriber_id)

    if group_id is not None:
        statement = statement.where(AuctionResult.group_id == group_id)

    filter_status_values = payout_status_filter_values(status) if status is not None and status.strip() else None
    if filter_status_values is not None:
        statement = statement.where(func.lower(Payout.status).in_(filter_status_values))

    statement = statement.order_by(Payout.created_at.desc(), Payout.id.desc())
    pagination = resolve_pagination(page, page_size)

    if pagination is None:
        payouts = db.scalars(statement).all()
        snapshot_map = build_membership_dues_snapshot_map(db, [payout.membership_id for payout in payouts])
        return [
            _serialize_payout(
                db,
                payout,
                dues_snapshot=snapshot_map.get(payout.membership_id),
            )
            for payout in payouts
        ]

    total_count = count_statement(db, statement)
    payouts = db.scalars(apply_pagination(statement, pagination)).all()
    snapshot_map = build_membership_dues_snapshot_map(db, [payout.membership_id for payout in payouts])
    return build_paginated_response(
        [
            _serialize_payout(
                db,
                payout,
                dues_snapshot=snapshot_map.get(payout.membership_id),
            )
            for payout in payouts
        ],
        pagination,
        total_count,
    )


def settle_owner_payout(
    db: Session,
    payout_id: int,
    current_user: CurrentUser,
    *,
    payout_method: str | None = None,
    payout_date: date | None = None,
    reference_no: str | None = None,
) -> dict:
    owner = require_owner(current_user)
    payout = db.scalar(
        select(Payout).where(
            Payout.id == payout_id,
            Payout.owner_id == owner.id,
        )
    )
    if payout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payout not found")

    normalized_status = normalize_payout_status(payout.status)
    audit_before = {
        "status": normalized_status,
        "payoutMethod": payout.payout_method,
        "payoutDate": payout.payout_date,
        "referenceNo": payout.reference_no,
    }
    payout.status = normalized_status
    if is_settled_payout_status(payout.status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payout already settled")

    payout.status = "settled"
    if payout_method is not None:
        payout.payout_method = payout_method
    payout.payout_date = payout_date or payout.payout_date or utcnow().date()
    if reference_no is not None:
        payout.reference_no = reference_no
    payout.updated_at = utcnow()
    payout_result = db.get(AuctionResult, payout.auction_result_id)
    if payout_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auction result not found")
    ledger_entry = _upsert_payout_ledger_entry(db, payout, payout_result)
    notify_payout_settled(db, payout=payout)
    log_audit_event(
        db,
        action="payout.settled",
        entity_type="payout",
        entity_id=payout.id,
        current_user=current_user,
        owner_id=owner.id,
        metadata={
            "auctionResultId": payout.auction_result_id,
            "groupId": payout_result.group_id,
            "membershipId": payout.membership_id,
            "payoutDate": payout.payout_date,
            "payoutId": payout.id,
            "payoutMethod": payout.payout_method,
            "referenceNo": payout.reference_no,
            "status": payout.status,
            "subscriberId": payout.subscriber_id,
            "deductionsAmount": money_int(payout.deductions_amount),
            "grossAmount": money_int(payout.gross_amount),
            "netAmount": money_int(payout.net_amount),
            "ledgerEntryId": ledger_entry.id,
        },
        before=audit_before,
        after={
            "status": payout.status,
            "payoutMethod": payout.payout_method,
            "payoutDate": payout.payout_date,
            "referenceNo": payout.reference_no,
            "ledgerEntryId": ledger_entry.id,
        },
    )
    db.commit()
    db.refresh(payout)
    db.refresh(ledger_entry)
    dispatch_staged_notifications(db)
    dues_snapshot = build_membership_dues_snapshot_map(db, [payout.membership_id]).get(payout.membership_id)
    return _serialize_payout(db, payout, dues_snapshot=dues_snapshot)
