"""add owner requests table

Revision ID: 20260423_0017
Revises: 20260422_0016
Create Date: 2026-04-23 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260423_0017"
down_revision: str | None = "20260422_0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_owner_requests_status"), "owner_requests", ["status"], unique=False)
    op.create_index(op.f("ix_owner_requests_user_id"), "owner_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_owner_requests_user_id"), table_name="owner_requests")
    op.drop_index(op.f("ix_owner_requests_status"), table_name="owner_requests")
    op.drop_table("owner_requests")
