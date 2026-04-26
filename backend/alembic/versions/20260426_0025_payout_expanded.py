"""Add payout expanded flag.

Revision ID: 20260426_0025
Revises: 20260426_0024
Create Date: 2026-04-26 20:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_0025"
down_revision = "20260426_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payouts",
        sa.Column(
            "payout_expanded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("payouts", "payout_expanded")
