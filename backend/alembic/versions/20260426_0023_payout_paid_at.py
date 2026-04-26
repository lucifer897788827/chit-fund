"""Add payout paid timestamp.

Revision ID: 20260426_0023
Revises: 20260426_0022
Create Date: 2026-04-26 17:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_0023"
down_revision = "20260426_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payouts") as batch_op:
        batch_op.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payouts") as batch_op:
        batch_op.drop_column("paid_at")
