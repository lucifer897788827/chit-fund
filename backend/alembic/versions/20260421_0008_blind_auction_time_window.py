"""add blind auction time window fields

Revision ID: 20260421_0008
Revises: 20260421_0007
Create Date: 2026-04-21 19:45:00.000000
"""

from datetime import timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260421_0008"
down_revision = "20260421_0007"
branch_labels = None
depends_on = None


auction_sessions_table = sa.table(
    "auction_sessions",
    sa.column("id", sa.Integer()),
    sa.column("auction_mode", sa.String(length=20)),
    sa.column("scheduled_start_at", sa.DateTime(timezone=True)),
    sa.column("actual_start_at", sa.DateTime(timezone=True)),
    sa.column("bidding_window_seconds", sa.Integer()),
    sa.column("start_time", sa.DateTime(timezone=True)),
    sa.column("end_time", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.add_column("auction_sessions", sa.Column("start_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auction_sessions", sa.Column("end_time", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    existing_sessions = bind.execute(
        sa.select(
            auction_sessions_table.c.id,
            auction_sessions_table.c.auction_mode,
            auction_sessions_table.c.scheduled_start_at,
            auction_sessions_table.c.actual_start_at,
            auction_sessions_table.c.bidding_window_seconds,
        )
    ).mappings()

    for session in existing_sessions:
        if (session["auction_mode"] or "").upper() != "BLIND":
            continue
        start_time = session["actual_start_at"] or session["scheduled_start_at"]
        if start_time is None:
            continue
        bidding_window_seconds = int(session["bidding_window_seconds"] or 0)
        end_time = start_time + timedelta(seconds=bidding_window_seconds)
        bind.execute(
            auction_sessions_table.update()
            .where(auction_sessions_table.c.id == session["id"])
            .values(start_time=start_time, end_time=end_time)
        )


def downgrade() -> None:
    op.drop_column("auction_sessions", "end_time")
    op.drop_column("auction_sessions", "start_time")
