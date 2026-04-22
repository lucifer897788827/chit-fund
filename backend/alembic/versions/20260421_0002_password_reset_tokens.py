from alembic import op
import sqlalchemy as sa


revision = "20260421_0002"
down_revision = "20260421_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_users_password_reset_token_hash"),
        "users",
        ["password_reset_token_hash"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_users_password_reset_token_hash"), table_name="users")
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_column("users", "password_reset_token_hash")
