from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_owner_created_at_id", "owner_id", "created_at", "id"),
        Index("ix_payments_owner_payment_date_id", "owner_id", "payment_date", "id"),
        Index(
            "ix_payments_owner_subscriber_payment_date_id",
            "owner_id",
            "subscriber_id",
            "payment_date",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), index=True)
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("group_memberships.id"), nullable=True)
    installment_id: Mapped[int | None] = mapped_column(ForeignKey("installments.id"), nullable=True)
    payment_type: Mapped[str] = mapped_column(String(30))
    payment_method: Mapped[str] = mapped_column(String(30))
    amount: Mapped[int] = mapped_column(Integer)
    payment_date: Mapped[date] = mapped_column(Date)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="recorded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Payout(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        Index("ix_payouts_owner_created_at_id", "owner_id", "created_at", "id"),
        Index(
            "ix_payouts_owner_subscriber_created_at_id",
            "owner_id",
            "subscriber_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    auction_result_id: Mapped[int] = mapped_column(ForeignKey("auction_results.id"), unique=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"))
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"))
    gross_amount: Mapped[int] = mapped_column(Integer)
    deductions_amount: Mapped[int] = mapped_column(Integer)
    net_amount: Mapped[int] = mapped_column(Integer)
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
    debit_amount: Mapped[int] = mapped_column(Integer)
    credit_amount: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
