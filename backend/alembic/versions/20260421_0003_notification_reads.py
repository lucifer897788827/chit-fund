from alembic import op
import sqlalchemy as sa


revision = "20260421_0003"
down_revision = "20260421_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("notifications", "read_at")
