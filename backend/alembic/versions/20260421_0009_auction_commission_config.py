"""add auction commission config

Revision ID: 20260421_0009
Revises: 20260421_0008
Create Date: 2026-04-21 20:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260421_0009"
down_revision = "20260421_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auction_sessions",
        sa.Column("commission_mode", sa.String(length=20), nullable=False, server_default="NONE"),
    )
    op.add_column(
        "auction_sessions",
        sa.Column("commission_value", sa.Numeric(precision=12, scale=2), nullable=True),
    )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("auction_sessions", "commission_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("auction_sessions", "commission_value")
    op.drop_column("auction_sessions", "commission_mode")
