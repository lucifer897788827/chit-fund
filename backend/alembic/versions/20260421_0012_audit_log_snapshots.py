"""add audit log snapshots

Revision ID: 20260421_0012
Revises: 20260421_0011
Create Date: 2026-04-21 21:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260421_0012"
down_revision: str | None = "20260421_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("before_json", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("after_json", sa.Text(), nullable=True))
    op.create_index(
        "ix_audit_logs_owner_created_at_id",
        "audit_logs",
        ["owner_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_owner_created_at_id", table_name="audit_logs")
    op.drop_column("audit_logs", "after_json")
    op.drop_column("audit_logs", "before_json")
