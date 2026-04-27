"""Add admin users performance indexes.

Revision ID: 20260427_0027
Revises: 20260427_0026
Create Date: 2026-04-27 18:05:00.000000
"""

from alembic import op


revision = "20260427_0027"
down_revision = "20260427_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_payouts_subscriber_id", "payouts", ["subscriber_id"], unique=False)
    op.create_index("ix_payments_recorded_by_user_id", "payments", ["recorded_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payments_recorded_by_user_id", table_name="payments")
    op.drop_index("ix_payouts_subscriber_id", table_name="payouts")
