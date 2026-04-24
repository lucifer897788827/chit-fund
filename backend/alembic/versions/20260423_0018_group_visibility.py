"""add group visibility

Revision ID: 20260423_0018
Revises: 20260423_0017
Create Date: 2026-04-23 13:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260423_0018"
down_revision: str | None = "20260423_0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chit_groups",
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("chit_groups", "visibility", server_default=None)


def downgrade() -> None:
    op.drop_column("chit_groups", "visibility")
