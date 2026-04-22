from decimal import Decimal
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChitGroup(Base):
    __tablename__ = "chit_groups"
    __table_args__ = (UniqueConstraint("owner_id", "group_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    group_code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    chit_value: Mapped[int] = mapped_column(Integer)
    installment_amount: Mapped[int] = mapped_column(Integer)
    member_count: Mapped[int] = mapped_column(Integer)
    cycle_count: Mapped[int] = mapped_column(Integer)
    cycle_frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    first_auction_date: Mapped[date] = mapped_column(Date)
    current_cycle_no: Mapped[int] = mapped_column(Integer, default=1)
    bidding_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    penalty_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    penalty_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    penalty_value: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grace_period_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "member_no"),
        UniqueConstraint("group_id", "subscriber_id"),
        Index("ix_group_memberships_group_id_membership_status", "group_id", "membership_status", "subscriber_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), index=True)
    member_no: Mapped[int] = mapped_column(Integer)
    membership_status: Mapped[str] = mapped_column(String(30), default="active")
    prized_status: Mapped[str] = mapped_column(String(30), default="unprized")
    prized_cycle_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    can_bid: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MembershipSlot(Base):
    __tablename__ = "membership_slots"
    __table_args__ = (
        UniqueConstraint("group_id", "slot_number"),
        Index("ix_membership_slots_group_user_has_won", "group_id", "user_id", "has_won"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    slot_number: Mapped[int] = mapped_column(Integer)
    has_won: Mapped[bool] = mapped_column(Boolean, default=False)


def membership_can_bid(membership: GroupMembership) -> bool:
    return membership.membership_status == "active" and membership.can_bid


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        UniqueConstraint("group_id", "membership_id", "cycle_no"),
        Index("ix_installments_group_id_status_due_date_id", "group_id", "status", "due_date", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    due_amount: Mapped[int] = mapped_column(Integer)
    penalty_amount: Mapped[int] = mapped_column(Integer, default=0)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)
    balance_amount: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    last_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
