from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser, require_owner
from app.models.auction import AuctionResult
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.money import Payment, Payout
from app.models.user import Subscriber
from app.modules.groups.slot_service import build_membership_slot_summary
from app.modules.payments.installment_service import build_membership_dues_snapshot_map
from app.modules.payments.validation import payout_status_filter_values


def _build_slot_summary_payload(db: Session, membership: GroupMembership) -> dict[str, int]:
    slot_summary = build_membership_slot_summary(db, membership)
    return {
        "slotCount": int(slot_summary.total_slots),
        "wonSlotCount": int(slot_summary.won_slots),
        "remainingSlotCount": int(slot_summary.available_slots),
    }


def list_payments(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)

    statement = (
        select(
            Payment,
            func.coalesce(GroupMembership.group_id, Installment.group_id).label("group_id"),
            func.coalesce(Payment.membership_id, Installment.membership_id).label("effective_membership_id"),
            Installment.cycle_no.label("cycle_no"),
        )
        .outerjoin(GroupMembership, GroupMembership.id == Payment.membership_id)
        .outerjoin(Installment, Installment.id == Payment.installment_id)
        .where(Payment.owner_id == owner.id)
    )

    if subscriber_id is not None:
        statement = statement.where(Payment.subscriber_id == subscriber_id)

    if group_id is not None:
        statement = statement.where(
            or_(
                GroupMembership.group_id == group_id,
                Installment.group_id == group_id,
            )
        )

    statement = statement.order_by(Payment.payment_date.desc(), Payment.id.desc())
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        rows = db.execute(statement).all()
        snapshot_map = build_membership_dues_snapshot_map(
            db,
            [membership_id for _payment, _group_id_value, membership_id, _cycle_no in rows if membership_id is not None],
        )
        return [
            {
                "id": payment.id,
                "ownerId": payment.owner_id,
                "subscriberId": payment.subscriber_id,
                "membershipId": payment.membership_id,
                "installmentId": payment.installment_id,
                "cycleNo": cycle_no,
                "groupId": group_id_value,
                "paymentType": payment.payment_type,
                "paymentMethod": payment.payment_method,
                "amount": money_int(payment.amount),
                "paymentDate": payment.payment_date,
                "referenceNo": payment.reference_no,
                "status": payment.status,
                **(
                    snapshot_map[membership_id].as_dict()
                    if membership_id is not None and membership_id in snapshot_map
                    else {}
                ),
            }
            for payment, group_id_value, membership_id, cycle_no in rows
        ]

    total_count = count_statement(db, statement)
    rows = db.execute(apply_pagination(statement, pagination)).all()
    snapshot_map = build_membership_dues_snapshot_map(
        db,
        [membership_id for _payment, _group_id_value, membership_id, _cycle_no in rows if membership_id is not None],
    )
    return build_paginated_response(
        [
            {
                "id": payment.id,
                "ownerId": payment.owner_id,
                "subscriberId": payment.subscriber_id,
                "membershipId": payment.membership_id,
                "installmentId": payment.installment_id,
                "cycleNo": cycle_no,
                "groupId": group_id_value,
                "paymentType": payment.payment_type,
                "paymentMethod": payment.payment_method,
                "amount": money_int(payment.amount),
                "paymentDate": payment.payment_date,
                "referenceNo": payment.reference_no,
                "status": payment.status,
                **(
                    snapshot_map[membership_id].as_dict()
                    if membership_id is not None and membership_id in snapshot_map
                    else {}
                ),
            }
            for payment, group_id_value, membership_id, cycle_no in rows
        ],
        pagination,
        total_count,
    )


def list_payouts(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    status: str | None = None,
    limit: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)

    statement = (
        select(
            Payout,
            AuctionResult.group_id.label("group_id"),
            ChitGroup.group_code,
            ChitGroup.title,
            AuctionResult.cycle_no,
            GroupMembership.member_no,
            Subscriber.full_name,
        )
        .join(AuctionResult, AuctionResult.id == Payout.auction_result_id)
        .join(GroupMembership, GroupMembership.id == Payout.membership_id)
        .join(ChitGroup, ChitGroup.id == AuctionResult.group_id)
        .join(Subscriber, Subscriber.id == Payout.subscriber_id)
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
        if limit is not None:
            statement = statement.limit(max(1, min(int(limit), 500)))
        rows = db.execute(statement).all()
        snapshot_map = build_membership_dues_snapshot_map(db, [payout.membership_id for payout, *_rest in rows])
        return [
            {
                "id": payout.id,
                "ownerId": payout.owner_id,
                "auctionResultId": payout.auction_result_id,
                "groupId": group_id,
                "groupCode": group_code,
                "groupTitle": group_title,
                "subscriberId": payout.subscriber_id,
                "subscriberName": subscriber_name,
                "membershipId": payout.membership_id,
                "memberNo": member_no,
                "cycleNo": cycle_no,
                "grossAmount": money_int(payout.gross_amount),
                "deductionsAmount": money_int(payout.deductions_amount),
                "netAmount": money_int(payout.net_amount),
                "payoutMethod": payout.payout_method,
                "payoutDate": payout.payout_date,
                "referenceNo": payout.reference_no,
                "status": payout.status,
                "createdAt": payout.created_at,
                **(
                    snapshot_map[payout.membership_id].as_dict()
                    if payout.membership_id in snapshot_map
                    else {}
                ),
            }
            for payout, group_id, group_code, group_title, cycle_no, member_no, subscriber_name in rows
        ]

    total_count = count_statement(db, statement)
    rows = db.execute(apply_pagination(statement, pagination)).all()
    snapshot_map = build_membership_dues_snapshot_map(db, [payout.membership_id for payout, *_rest in rows])
    return build_paginated_response(
        [
            {
                "id": payout.id,
                "ownerId": payout.owner_id,
                "auctionResultId": payout.auction_result_id,
                "groupId": group_id,
                "groupCode": group_code,
                "groupTitle": group_title,
                "subscriberId": payout.subscriber_id,
                "subscriberName": subscriber_name,
                "membershipId": payout.membership_id,
                "memberNo": member_no,
                "cycleNo": cycle_no,
                "grossAmount": money_int(payout.gross_amount),
                "deductionsAmount": money_int(payout.deductions_amount),
                "netAmount": money_int(payout.net_amount),
                "payoutMethod": payout.payout_method,
                "payoutDate": payout.payout_date,
                "referenceNo": payout.reference_no,
                "status": payout.status,
                "createdAt": payout.created_at,
                **(
                    snapshot_map[payout.membership_id].as_dict()
                    if payout.membership_id in snapshot_map
                    else {}
                ),
            }
            for payout, group_id, group_code, group_title, cycle_no, member_no, subscriber_name in rows
        ],
        pagination,
        total_count,
    )


def get_member_outstanding_totals(
    db: Session,
    current_user: CurrentUser,
    subscriber_id: int | None = None,
    group_id: int | None = None,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    owner = require_owner(current_user)

    statement = (
        select(GroupMembership)
        .join(ChitGroup, ChitGroup.id == GroupMembership.group_id)
        .where(ChitGroup.owner_id == owner.id)
    )

    if subscriber_id is not None:
        statement = statement.where(GroupMembership.subscriber_id == subscriber_id)

    if group_id is not None:
        statement = statement.where(GroupMembership.group_id == group_id)

    statement = statement.order_by(GroupMembership.group_id.asc(), GroupMembership.member_no.asc())
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        memberships = db.scalars(statement).all()
        snapshot_map = build_membership_dues_snapshot_map(db, [membership.id for membership in memberships])
        return [
            {
                "groupId": membership.group_id,
                "subscriberId": membership.subscriber_id,
                "membershipId": membership.id,
                "memberNo": membership.member_no,
                **_build_slot_summary_payload(db, membership),
                **snapshot_map[membership.id].as_dict(),
            }
            for membership in memberships
        ]

    total_count = count_statement(db, statement)
    memberships = db.scalars(apply_pagination(statement, pagination)).all()
    snapshot_map = build_membership_dues_snapshot_map(db, [membership.id for membership in memberships])
    return build_paginated_response(
        [
            {
                "groupId": membership.group_id,
                "subscriberId": membership.subscriber_id,
                "membershipId": membership.id,
                "memberNo": membership.member_no,
                **_build_slot_summary_payload(db, membership),
                **snapshot_map[membership.id].as_dict(),
            }
            for membership in memberships
        ],
        pagination,
        total_count,
    )
