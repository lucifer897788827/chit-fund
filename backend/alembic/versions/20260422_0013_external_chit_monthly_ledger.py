"""add external chit monthly ledger fields

Revision ID: 20260422_0013
Revises: 20260421_0012
Create Date: 2026-04-22 13:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260422_0013"
down_revision: str | None = "20260421_0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("external_chits") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("monthly_installment", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("total_members", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("total_months", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("user_slots", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("first_month_organizer", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key(
            "fk_external_chits_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )
        batch_op.create_index("ix_external_chits_user_id", ["user_id"], unique=False)

    op.execute(
        """
        UPDATE external_chits
        SET
            user_id = (
                SELECT subscribers.user_id
                FROM subscribers
                WHERE subscribers.id = external_chits.subscriber_id
            ),
            name = COALESCE(name, title),
            monthly_installment = COALESCE(monthly_installment, CAST(installment_amount AS INTEGER)),
            user_slots = COALESCE(user_slots, 1)
        """
    )

    with op.batch_alter_table("external_chit_entries") as batch_op:
        batch_op.add_column(sa.Column("month_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("bid_amount", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("winner_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("winner_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("share_per_slot", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("my_share", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("my_payable", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("my_payout", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("is_bid_overridden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_share_overridden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_payable_overridden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_payout_overridden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.create_index(
            "ix_external_chit_entries_chit_month_number",
            ["external_chit_id", "month_number"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("external_chit_entries") as batch_op:
        batch_op.drop_index("ix_external_chit_entries_chit_month_number")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("is_payout_overridden")
        batch_op.drop_column("is_payable_overridden")
        batch_op.drop_column("is_share_overridden")
        batch_op.drop_column("is_bid_overridden")
        batch_op.drop_column("my_payout")
        batch_op.drop_column("my_payable")
        batch_op.drop_column("my_share")
        batch_op.drop_column("share_per_slot")
        batch_op.drop_column("winner_name")
        batch_op.drop_column("winner_type")
        batch_op.drop_column("bid_amount")
        batch_op.drop_column("month_number")

    with op.batch_alter_table("external_chits") as batch_op:
        batch_op.drop_index("ix_external_chits_user_id")
        batch_op.drop_constraint("fk_external_chits_user_id_users", type_="foreignkey")
        batch_op.drop_column("first_month_organizer")
        batch_op.drop_column("user_slots")
        batch_op.drop_column("total_months")
        batch_op.drop_column("total_members")
        batch_op.drop_column("monthly_installment")
        batch_op.drop_column("name")
        batch_op.drop_column("user_id")
