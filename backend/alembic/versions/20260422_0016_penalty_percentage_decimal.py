"""restore decimal storage for penalty percentages

Revision ID: 20260422_0016
Revises: 20260422_0015
Create Date: 2026-04-22 22:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260422_0016"
down_revision: str | None = "20260422_0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                'ALTER TABLE "chit_groups" ALTER COLUMN "penalty_value" TYPE NUMERIC(5, 2) '
                'USING "penalty_value"::NUMERIC(5, 2)'
            )
        )
        return

    with op.batch_alter_table("chit_groups") as batch_op:
        batch_op.alter_column("penalty_value", existing_type=sa.Integer(), type_=sa.Numeric(5, 2))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                'ALTER TABLE "chit_groups" ALTER COLUMN "penalty_value" TYPE INTEGER '
                'USING FLOOR(COALESCE("penalty_value", 0))::INTEGER'
            )
        )
        return

    with op.batch_alter_table("chit_groups") as batch_op:
        batch_op.alter_column("penalty_value", existing_type=sa.Numeric(5, 2), type_=sa.Integer())
