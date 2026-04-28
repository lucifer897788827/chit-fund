"""attach membership slots to memberships

Revision ID: 20260428_0030
Revises: 20260428_0029
Create Date: 2026-04-28 13:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260428_0030"
down_revision = "20260428_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("membership_slots", sa.Column("membership_id", sa.Integer(), nullable=True))
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_membership_slots_membership_id_group_memberships",
            "membership_slots",
            "group_memberships",
            ["membership_id"],
            ["id"],
        )
    op.create_index("ix_membership_slots_membership_id", "membership_slots", ["membership_id"], unique=False)
    op.create_index(
        "ix_membership_slots_group_membership_has_won",
        "membership_slots",
        ["group_id", "membership_id", "has_won"],
        unique=False,
    )
    op.execute(
        """
        UPDATE membership_slots
        SET membership_id = (
            SELECT gm.id
            FROM group_memberships AS gm
            JOIN subscribers AS s ON s.id = gm.subscriber_id
            WHERE gm.group_id = membership_slots.group_id
              AND s.user_id = membership_slots.user_id
            ORDER BY gm.id ASC
            LIMIT 1
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_membership_slots_group_membership_has_won", table_name="membership_slots")
    op.drop_index("ix_membership_slots_membership_id", table_name="membership_slots")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_membership_slots_membership_id_group_memberships", "membership_slots", type_="foreignkey")
    op.drop_column("membership_slots", "membership_id")
