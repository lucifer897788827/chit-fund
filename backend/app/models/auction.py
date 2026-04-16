from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuctionSession(Base):
    __tablename__ = "auction_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bidding_window_seconds: Mapped[int] = mapped_column(Integer, default=180)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    opened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    winning_bid_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuctionBid(Base):
    __tablename__ = "auction_bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.id"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"), index=True)
    bidder_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bid_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    bid_discount_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_valid: Mapped[bool] = mapped_column(default=True)
    invalid_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_bid_id: Mapped[int | None] = mapped_column(nullable=True)


class AuctionResult(Base):
    __tablename__ = "auction_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.id"), unique=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    winner_membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"))
    winning_bid_id: Mapped[int] = mapped_column(ForeignKey("auction_bids.id"))
    winning_bid_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    dividend_pool_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    dividend_per_member_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    owner_commission_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    winner_payout_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    finalized_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
