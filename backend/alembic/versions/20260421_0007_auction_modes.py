from alembic import op
import sqlalchemy as sa


revision = "20260421_0007"
down_revision = "20260421_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "auction_sessions",
        sa.Column("auction_mode", sa.String(length=20), nullable=False, server_default="LIVE"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("auction_sessions", "auction_mode", server_default=None)


def downgrade():
    op.drop_column("auction_sessions", "auction_mode")
