from alembic import op
import sqlalchemy as sa


revision = "20260421_0004"
down_revision = "20260421_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index(op.f("ix_job_runs_task_name"), "job_runs", ["task_name"], unique=False)
    op.create_index(op.f("ix_job_runs_task_id"), "job_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_job_runs_status"), "job_runs", ["status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_job_runs_status"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_task_id"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_task_name"), table_name="job_runs")
    op.drop_table("job_runs")
