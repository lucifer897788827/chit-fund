"""add owner scope to job runs

Revision ID: 20260422_0015
Revises: 20260422_0014
Create Date: 2026-04-22 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_0015"
down_revision = "20260422_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_job_runs_owner_id_started_at_id", ["owner_id", "started_at", "id"], unique=False)
        batch_op.create_foreign_key("fk_job_runs_owner_id_owners", "owners", ["owner_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("job_runs") as batch_op:
        batch_op.drop_constraint("fk_job_runs_owner_id_owners", type_="foreignkey")
        batch_op.drop_index("ix_job_runs_owner_id_started_at_id")
        batch_op.drop_column("owner_id")
