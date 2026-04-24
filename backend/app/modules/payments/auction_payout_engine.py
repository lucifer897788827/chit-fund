from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Subscriber
from app.modules.auctions.commission_service import calculate_owner_commission_amount


@dataclass(frozen=True, slots=True)
class MembershipPayableBreakdown:
    membership_id: int
    subscriber_id: int
    slot_count: int
    member_payable_amount: int


@dataclass(frozen=True, slots=True)
class AuctionPayoutCalculation:
    total_slots: int
    winning_bid_amount: int
    owner_commission_amount: int
    net_bid_amount: int
    dividend_pool_amount: int
    dividend_per_member_amount: int
    winner_payout_amount: int
    winner_deductions_amount: int
    winner_membership_id: int
    winner_slot_count: int
    winner_member_payable_amount: int
    rounding_adjustment_amount: int
    membership_payables: tuple[MembershipPayableBreakdown, ...]


def _build_membership_slot_count_map(
    db: Session,
    memberships: list[GroupMembership],
) -> dict[int, int]:
    if not memberships:
        return {}

    subscriber_ids = sorted({membership.subscriber_id for membership in memberships})
    subscriber_user_ids = {
        int(subscriber_id): int(user_id)
        for subscriber_id, user_id in db.execute(
            select(Subscriber.id, Subscriber.user_id).where(Subscriber.id.in_(subscriber_ids))
        ).all()
    }
    user_ids = sorted({user_id for user_id in subscriber_user_ids.values()})
    if not user_ids:
        return {membership.id: 1 for membership in memberships}

    slot_counts_by_user_id = {
        int(user_id): int(slot_count)
        for user_id, slot_count in db.execute(
            select(
                MembershipSlot.user_id,
                func.count(MembershipSlot.id),
            )
            .where(
                MembershipSlot.group_id == memberships[0].group_id,
                MembershipSlot.user_id.in_(user_ids),
            )
            .group_by(MembershipSlot.user_id)
        ).all()
    }

    membership_slot_counts: dict[int, int] = {}
    for membership in memberships:
        user_id = subscriber_user_ids.get(int(membership.subscriber_id))
        membership_slot_counts[membership.id] = max(int(slot_counts_by_user_id.get(user_id, 0)), 1)
    return membership_slot_counts


def calculate_payout(
    db: Session,
    *,
    session: AuctionSession,
    group: ChitGroup,
    winning_bid: AuctionBid,
    winner_membership_id: int,
) -> AuctionPayoutCalculation:
    total_slots = max(int(group.member_count or 0), 1)
    winning_bid_amount = money_int(winning_bid.bid_amount)
    chit_value = money_int(group.chit_value)
    installment_amount = money_int(group.installment_amount)

    if (session.auction_mode or "").strip().upper() == "FIXED":
        memberships = db.scalars(
            select(GroupMembership)
            .where(GroupMembership.group_id == group.id)
            .order_by(GroupMembership.member_no.asc(), GroupMembership.id.asc())
        ).all()
        membership_slot_counts = _build_membership_slot_count_map(db, memberships)

        membership_payables: list[MembershipPayableBreakdown] = []
        winner_slot_count = 1
        winner_member_payable_amount = installment_amount
        for membership in memberships:
            slot_count = membership_slot_counts.get(membership.id, 1)
            member_payable_amount = installment_amount * slot_count
            membership_payables.append(
                MembershipPayableBreakdown(
                    membership_id=membership.id,
                    subscriber_id=membership.subscriber_id,
                    slot_count=slot_count,
                    member_payable_amount=member_payable_amount,
                )
            )
            if membership.id == winner_membership_id:
                winner_slot_count = slot_count
                winner_member_payable_amount = member_payable_amount

        winner_payout_amount = chit_value - installment_amount
        winner_deductions_amount = chit_value - winner_payout_amount

        return AuctionPayoutCalculation(
            total_slots=total_slots,
            winning_bid_amount=winning_bid_amount,
            owner_commission_amount=0,
            net_bid_amount=0,
            dividend_pool_amount=0,
            dividend_per_member_amount=0,
            winner_payout_amount=winner_payout_amount,
            winner_deductions_amount=winner_deductions_amount,
            winner_membership_id=winner_membership_id,
            winner_slot_count=winner_slot_count,
            winner_member_payable_amount=winner_member_payable_amount,
            rounding_adjustment_amount=0,
            membership_payables=tuple(membership_payables),
        )

    owner_commission_amount = calculate_owner_commission_amount(
        session=session,
        group=group,
        winning_bid_amount=winning_bid_amount,
    )
    net_bid_amount = max(winning_bid_amount - owner_commission_amount, 0)
    share_per_slot_amount = net_bid_amount // total_slots
    rounding_adjustment_amount = net_bid_amount % total_slots
    winner_payout_amount = chit_value - winning_bid_amount - installment_amount + share_per_slot_amount
    winner_deductions_amount = chit_value - winner_payout_amount

    memberships = db.scalars(
        select(GroupMembership)
        .where(GroupMembership.group_id == group.id)
        .order_by(GroupMembership.member_no.asc(), GroupMembership.id.asc())
    ).all()
    membership_slot_counts = _build_membership_slot_count_map(db, memberships)

    membership_payables: list[MembershipPayableBreakdown] = []
    winner_slot_count = 1
    winner_member_payable_amount = installment_amount - share_per_slot_amount

    for membership in memberships:
        slot_count = membership_slot_counts.get(membership.id, 1)
        member_payable_amount = (installment_amount * slot_count) - (share_per_slot_amount * slot_count)
        membership_payables.append(
            MembershipPayableBreakdown(
                membership_id=membership.id,
                subscriber_id=membership.subscriber_id,
                slot_count=slot_count,
                member_payable_amount=member_payable_amount,
            )
        )
        if membership.id == winner_membership_id:
            winner_slot_count = slot_count
            winner_member_payable_amount = member_payable_amount

    return AuctionPayoutCalculation(
        total_slots=total_slots,
        winning_bid_amount=winning_bid_amount,
        owner_commission_amount=owner_commission_amount,
        net_bid_amount=net_bid_amount,
        dividend_pool_amount=net_bid_amount,
        dividend_per_member_amount=share_per_slot_amount,
        winner_payout_amount=winner_payout_amount,
        winner_deductions_amount=winner_deductions_amount,
        winner_membership_id=winner_membership_id,
        winner_slot_count=winner_slot_count,
        winner_member_payable_amount=winner_member_payable_amount,
        rounding_adjustment_amount=rounding_adjustment_amount,
        membership_payables=tuple(membership_payables),
    )


def build_membership_payables_from_result(
    db: Session,
    *,
    result: AuctionResult,
    group: ChitGroup | None = None,
) -> tuple[MembershipPayableBreakdown, ...]:
    payout_group = group or db.get(ChitGroup, result.group_id)
    if payout_group is None:
        raise ValueError("Chit group not found for payout calculation")

    installment_amount = money_int(payout_group.installment_amount)
    share_per_slot_amount = money_int(result.dividend_per_member_amount)
    memberships = db.scalars(
        select(GroupMembership)
        .where(GroupMembership.group_id == payout_group.id)
        .order_by(GroupMembership.member_no.asc(), GroupMembership.id.asc())
    ).all()
    membership_slot_counts = _build_membership_slot_count_map(db, memberships)

    payables: list[MembershipPayableBreakdown] = []
    for membership in memberships:
        slot_count = membership_slot_counts.get(membership.id, 1)
        member_payable_amount = (installment_amount * slot_count) - (share_per_slot_amount * slot_count)
        payables.append(
            MembershipPayableBreakdown(
                membership_id=membership.id,
                subscriber_id=membership.subscriber_id,
                slot_count=slot_count,
                member_payable_amount=member_payable_amount,
            )
        )

    return tuple(payables)
