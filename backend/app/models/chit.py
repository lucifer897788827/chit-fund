from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChitGroup(Base):
    __tablename__ = "chit_groups"
    __table_args__ = (UniqueConstraint("owner_id", "group_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    group_code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    chit_value: Mapped[float] = mapped_column(Numeric(12, 2))
    installment_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    member_count: Mapped[int] = mapped_column(Integer)
    cycle_count: Mapped[int] = mapped_column(Integer)
    cycle_frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    first_auction_date: Mapped[date] = mapped_column(Date)
    current_cycle_no: Mapped[int] = mapped_column(Integer, default=1)
    bidding_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "member_no"),
        UniqueConstraint("group_id", "subscriber_id"),
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


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (UniqueConstraint("group_id", "membership_id", "cycle_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    due_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    penalty_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    balance_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    last_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
