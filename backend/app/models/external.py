from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.core.database import Base


class ExternalChit(Base):
    __tablename__ = "external_chits"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer_name: Mapped[str] = mapped_column(String(255))
    chit_value: Mapped[int] = mapped_column(Integer)
    installment_amount: Mapped[int] = mapped_column(Integer)
    monthly_installment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_members: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_slots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_month_organizer: Mapped[bool] = mapped_column(Boolean, default=False)
    cycle_frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalChitEntry(Base):
    __tablename__ = "external_chit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_chit_id: Mapped[int] = mapped_column(ForeignKey("external_chits.id"), index=True)
    month_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    winner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    share_per_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    my_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    my_payable: Mapped[int | None] = mapped_column(Integer, nullable=True)
    my_payout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_bid_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_share_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_payable_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_payout_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    entry_type: Mapped[str] = mapped_column(String(30))
    entry_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
