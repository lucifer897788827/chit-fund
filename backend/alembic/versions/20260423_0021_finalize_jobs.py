"""Add durable finalize jobs queue.

Revision ID: 20260423_0021
Revises: 20260423_0020
Create Date: 2026-04-23 23:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260423_0021"
down_revision = "20260423_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finalize_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auction_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auction_id"], ["auction_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auction_id"),
    )
    op.create_index("ix_finalize_jobs_auction_id", "finalize_jobs", ["auction_id"], unique=False)
    op.create_index(
        "ix_finalize_jobs_status_created_at_id",
        "finalize_jobs",
        ["status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_finalize_jobs_status_updated_at_id",
        "finalize_jobs",
        ["status", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_finalize_jobs_status_updated_at_id", table_name="finalize_jobs")
    op.drop_index("ix_finalize_jobs_status_created_at_id", table_name="finalize_jobs")
    op.drop_index("ix_finalize_jobs_auction_id", table_name="finalize_jobs")
    op.drop_table("finalize_jobs")
