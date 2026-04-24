"""Add payment dedupe and ledger source unique indexes.

Revision ID: 20260423_0020
Revises: 20260423_0019
Create Date: 2026-04-23 19:45:00.000000
"""

from alembic import op


revision = "20260423_0020"
down_revision = "20260423_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX ux_payments_request_dedupe
        ON payments (
            owner_id,
            subscriber_id,
            coalesce(membership_id, -1),
            coalesce(installment_id, -1),
            payment_type,
            payment_method,
            amount,
            payment_date,
            coalesce(reference_no, '__null__')
        )
        """
    )
    op.create_index(
        "ux_ledger_entries_source",
        "ledger_entries",
        ["source_table", "source_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_ledger_entries_source", table_name="ledger_entries")
    op.drop_index("ux_payments_request_dedupe", table_name="payments")
