"""add group join requests

Revision ID: 20260428_0029
Revises: 20260428_0028
Create Date: 2026-04-28 13:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260428_0029"
down_revision = "20260428_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_join_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("requested_slot_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("approved_membership_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_membership_id"], ["group_memberships.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_group_join_requests_group_status_created",
        "group_join_requests",
        ["group_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_group_join_requests_subscriber_group_status",
        "group_join_requests",
        ["subscriber_id", "group_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_group_join_requests_subscriber_group_status", table_name="group_join_requests")
    op.drop_index("ix_group_join_requests_group_status_created", table_name="group_join_requests")
    op.drop_table("group_join_requests")
