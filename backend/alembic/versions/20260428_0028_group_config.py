"""add group configuration fields

Revision ID: 20260428_0028
Revises: 20260427_0027
Create Date: 2026-04-28 12:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260428_0028"
down_revision = "20260427_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chit_groups",
        sa.Column("commission_type", sa.String(length=30), nullable=False, server_default="NONE"),
    )
    op.add_column(
        "chit_groups",
        sa.Column("auction_type", sa.String(length=30), nullable=False, server_default="LIVE"),
    )
    op.add_column(
        "chit_groups",
        sa.Column("group_type", sa.String(length=30), nullable=False, server_default="STANDARD"),
    )
    op.add_column(
        "chit_groups",
        sa.Column("auto_cycle_calculation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("chit_groups", "commission_type", server_default=None)
        op.alter_column("chit_groups", "auction_type", server_default=None)
        op.alter_column("chit_groups", "group_type", server_default=None)
        op.alter_column("chit_groups", "auto_cycle_calculation", server_default=None)


def downgrade() -> None:
    op.drop_column("chit_groups", "auto_cycle_calculation")
    op.drop_column("chit_groups", "group_type")
    op.drop_column("chit_groups", "auction_type")
    op.drop_column("chit_groups", "commission_type")
