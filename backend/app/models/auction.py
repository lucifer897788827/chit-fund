from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuctionSession(Base):
    __tablename__ = "auction_sessions"
    __table_args__ = (
        Index("ix_auction_sessions_status_id", "status", "id"),
        Index("ix_auction_sessions_group_created_at_id", "group_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auction_mode: Mapped[str] = mapped_column(String(20), default="LIVE")
    commission_mode: Mapped[str] = mapped_column(String(20), default="NONE")
    commission_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_bid_value: Mapped[int] = mapped_column(Integer, default=0)
    max_bid_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_increment: Mapped[int] = mapped_column(Integer, default=1)
    bidding_window_seconds: Mapped[int] = mapped_column(Integer, default=180)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    opened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    winning_bid_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuctionBid(Base):
    __tablename__ = "auction_bids"

    __table_args__ = (
        UniqueConstraint("auction_session_id", "bidder_user_id", "idempotency_key"),
        Index(
            "ix_auction_bids_session_valid_bid_amount_placed_at_id",
            "auction_session_id",
            "is_valid",
            "bid_amount",
            "placed_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.id"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"), index=True)
    bidder_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    bid_amount: Mapped[int] = mapped_column(Integer)
    bid_discount_amount: Mapped[int] = mapped_column(Integer)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_valid: Mapped[bool] = mapped_column(default=True)
    invalid_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_bid_id: Mapped[int | None] = mapped_column(nullable=True)


Index(
    "ix_auction_bids_session_bid_amount_desc_placed_at_id",
    AuctionBid.auction_session_id,
    AuctionBid.bid_amount.desc(),
    AuctionBid.placed_at,
    AuctionBid.id,
)


class AuctionResult(Base):
    __tablename__ = "auction_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.id"), unique=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("chit_groups.id"), index=True)
    cycle_no: Mapped[int] = mapped_column(Integer)
    winner_membership_id: Mapped[int] = mapped_column(ForeignKey("group_memberships.id"))
    winning_bid_id: Mapped[int] = mapped_column(ForeignKey("auction_bids.id"))
    winning_bid_amount: Mapped[int] = mapped_column(Integer)
    dividend_pool_amount: Mapped[int] = mapped_column(Integer)
    dividend_per_member_amount: Mapped[int] = mapped_column(Integer)
    owner_commission_amount: Mapped[int] = mapped_column(Integer)
    winner_payout_amount: Mapped[int] = mapped_column(Integer)
    finalized_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class FinalizeJob(Base):
    __tablename__ = "finalize_jobs"
    __table_args__ = (
        UniqueConstraint("auction_id"),
        Index("ix_finalize_jobs_status_created_at_id", "status", "created_at", "id"),
        Index("ix_finalize_jobs_status_updated_at_id", "status", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
