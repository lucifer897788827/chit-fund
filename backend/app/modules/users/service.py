from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import money_int
from app.core.security import CurrentUser
from app.models.auction import AuctionResult
from app.models.chit import GroupMembership, MembershipSlot
from app.models.money import Payment, Payout


def get_my_financial_summary(db: Session, current_user: CurrentUser) -> dict:
    subscriber = current_user.subscriber
    if subscriber is None:
        return {
            "total_paid": 0,
            "total_received": 0,
            "dividend": 0,
            "net": 0,
        }

    total_paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.subscriber_id == subscriber.id)
    ) or 0
    total_received = db.scalar(
        select(func.coalesce(func.sum(Payout.net_amount), 0)).where(Payout.subscriber_id == subscriber.id)
    ) or 0

    memberships = db.scalars(select(GroupMembership).where(GroupMembership.subscriber_id == subscriber.id)).all()
    dividend = 0
    for membership in memberships:
        slot_count = db.scalar(
            select(func.count(MembershipSlot.id)).where(
                MembershipSlot.group_id == membership.group_id,
                MembershipSlot.user_id == current_user.user.id,
            )
        ) or 0
        effective_slot_count = max(int(slot_count), 1)
        group_dividend = db.scalar(
            select(func.coalesce(func.sum(AuctionResult.dividend_per_member_amount), 0)).where(
                AuctionResult.group_id == membership.group_id
            )
        ) or 0
        dividend += money_int(group_dividend) * effective_slot_count

    total_paid_value = money_int(total_paid)
    total_received_value = money_int(total_received)
    dividend_value = money_int(dividend)
    return {
        "total_paid": total_paid_value,
        "total_received": total_received_value,
        "dividend": dividend_value,
        "net": total_received_value + dividend_value - total_paid_value,
    }
