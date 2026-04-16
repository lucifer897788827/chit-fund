from alembic import op


revision = "20260415_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("select 1")


def downgrade():
    op.execute("select 1")
