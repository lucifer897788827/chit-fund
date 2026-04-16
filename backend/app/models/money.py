from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), index=True)
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("group_memberships.id"), nullable=True)
    installment_id: Mapped[int | None] = mapped_column(ForeignKey("installments.id"), nullable=True)
    payment_type: Mapped[str] = mapped_column(String(30))
    payment_method: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    payment_date: Mapped[date] = mapped_column(Date)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="recorded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    auction_result_id: Mapped[int] = mapped_column(ForeignKey("auction_results.id"), unique=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"))
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"))
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    deductions_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    net_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    payout_method: Mapped[str] = mapped_column(String(30))
    payout_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date)
    entry_type: Mapped[str] = mapped_column(String(30))
    source_table: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[int] = mapped_column()
    subscriber_id: Mapped[int | None] = mapped_column(ForeignKey("subscribers.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("chit_groups.id"), nullable=True)
    debit_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    credit_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
