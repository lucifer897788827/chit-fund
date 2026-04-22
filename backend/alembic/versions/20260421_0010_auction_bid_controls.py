"""add auction bid controls

Revision ID: 20260421_0010
Revises: 20260421_0009
Create Date: 2026-04-21 21:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260421_0010"
down_revision = "20260421_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auction_sessions",
        sa.Column("min_bid_value", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "auction_sessions",
        sa.Column("max_bid_value", sa.Integer(), nullable=True),
    )
    op.add_column(
        "auction_sessions",
        sa.Column("min_increment", sa.Integer(), nullable=False, server_default="1"),
    )

    op.execute(
        sa.text(
            """
            update auction_sessions
            set max_bid_value = (
                select cast(chit_groups.chit_value as integer)
                from chit_groups
                where chit_groups.id = auction_sessions.group_id
            )
            where auction_sessions.max_bid_value is null
            """
        )
    )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("auction_sessions", "min_bid_value", server_default=None)
        op.alter_column("auction_sessions", "min_increment", server_default=None)


def downgrade() -> None:
    op.drop_column("auction_sessions", "min_increment")
    op.drop_column("auction_sessions", "max_bid_value")
    op.drop_column("auction_sessions", "min_bid_value")
