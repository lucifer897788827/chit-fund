from alembic import op
import sqlalchemy as sa


revision = "20260423_0019"
down_revision = "20260423_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_auction_bids_session_bid_amount_desc_placed_at_id",
        "auction_bids",
        [
            sa.text("auction_session_id"),
            sa.text("bid_amount DESC"),
            sa.text("placed_at"),
            sa.text("id"),
        ],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_auction_bids_session_bid_amount_desc_placed_at_id", table_name="auction_bids")
