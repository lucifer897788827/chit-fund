"""Add subscriber auto-created flag.

Revision ID: 20260427_0026
Revises: 20260426_0025
Create Date: 2026-04-27 15:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0026"
down_revision = "20260426_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscribers",
        sa.Column(
            "auto_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("subscribers", "auto_created")
