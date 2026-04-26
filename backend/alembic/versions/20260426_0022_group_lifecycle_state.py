"""Add group lifecycle state.

Revision ID: 20260426_0022
Revises: 20260423_0021
Create Date: 2026-04-26 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_0022"
down_revision = "20260423_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chit_groups") as batch_op:
        batch_op.add_column(sa.Column("collection_closed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("current_month_status", sa.String(length=30), nullable=False, server_default="OPEN"))


def downgrade() -> None:
    with op.batch_alter_table("chit_groups") as batch_op:
        batch_op.drop_column("current_month_status")
        batch_op.drop_column("collection_closed")
