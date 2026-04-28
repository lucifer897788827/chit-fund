"""add group invite audit history

Revision ID: 20260428_0031
Revises: 20260428_0030
Create Date: 2026-04-28 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260428_0031"
down_revision = "20260428_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=False),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["group_memberships.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_group_invites_group_status_issued",
        "group_invites",
        ["group_id", "status", "issued_at"],
        unique=False,
    )
    op.create_index(
        "ix_group_invites_group_subscriber_issued",
        "group_invites",
        ["group_id", "subscriber_id", "issued_at"],
        unique=False,
    )
    op.create_index("ix_group_invites_membership_id", "group_invites", ["membership_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_group_invites_membership_id", table_name="group_invites")
    op.drop_index("ix_group_invites_group_subscriber_issued", table_name="group_invites")
    op.drop_index("ix_group_invites_group_status_issued", table_name="group_invites")
    op.drop_table("group_invites")
