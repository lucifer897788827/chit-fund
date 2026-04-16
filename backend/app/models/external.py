from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExternalChit(Base):
    __tablename__ = "external_chits"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    organizer_name: Mapped[str] = mapped_column(String(255))
    chit_value: Mapped[float] = mapped_column(Numeric(12, 2))
    installment_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    cycle_frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExternalChitEntry(Base):
    __tablename__ = "external_chit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_chit_id: Mapped[int] = mapped_column(ForeignKey("external_chits.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(30))
    entry_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
