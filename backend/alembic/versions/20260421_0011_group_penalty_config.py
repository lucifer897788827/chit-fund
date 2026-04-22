"""add group penalty config

Revision ID: 20260421_0011
Revises: 20260421_0010
Create Date: 2026-04-21 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260421_0011"
down_revision: str | None = "20260421_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chit_groups",
        sa.Column("penalty_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "chit_groups",
        sa.Column("penalty_type", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "chit_groups",
        sa.Column("penalty_value", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "chit_groups",
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="0"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("chit_groups", "penalty_enabled", server_default=None)
        op.alter_column("chit_groups", "grace_period_days", server_default=None)


def downgrade() -> None:
    op.drop_column("chit_groups", "grace_period_days")
    op.drop_column("chit_groups", "penalty_value")
    op.drop_column("chit_groups", "penalty_type")
    op.drop_column("chit_groups", "penalty_enabled")
