"""Add admin messages.

Revision ID: 20260426_0024
Revises: 20260426_0023
Create Date: 2026-04-26 18:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_0024"
down_revision = "20260426_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_messages_active_created_at_id",
        "admin_messages",
        ["active", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_messages_active_created_at_id", table_name="admin_messages")
    op.drop_table("admin_messages")
