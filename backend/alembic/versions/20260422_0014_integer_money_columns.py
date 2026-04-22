"""convert money columns to integers

Revision ID: 20260422_0014
Revises: 20260422_0013
Create Date: 2026-04-22 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260422_0014"
down_revision = "20260422_0013"
branch_labels = None
depends_on = None


_COLUMN_CHANGES: tuple[tuple[str, str], ...] = (
    ("chit_groups", "chit_value"),
    ("chit_groups", "installment_amount"),
    ("chit_groups", "penalty_value"),
    ("installments", "due_amount"),
    ("installments", "penalty_amount"),
    ("installments", "paid_amount"),
    ("installments", "balance_amount"),
    ("auction_sessions", "commission_value"),
    ("auction_bids", "bid_amount"),
    ("auction_bids", "bid_discount_amount"),
    ("auction_results", "winning_bid_amount"),
    ("auction_results", "dividend_pool_amount"),
    ("auction_results", "dividend_per_member_amount"),
    ("auction_results", "owner_commission_amount"),
    ("auction_results", "winner_payout_amount"),
    ("payments", "amount"),
    ("payouts", "gross_amount"),
    ("payouts", "deductions_amount"),
    ("payouts", "net_amount"),
    ("ledger_entries", "debit_amount"),
    ("ledger_entries", "credit_amount"),
    ("external_chits", "chit_value"),
    ("external_chits", "installment_amount"),
    ("external_chit_entries", "amount"),
)


def _upgrade_postgresql() -> None:
    for table_name, column_name in _COLUMN_CHANGES:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE INTEGER '
                f'USING FLOOR(COALESCE("{column_name}", 0))::INTEGER'
            )
        )


def _downgrade_postgresql() -> None:
    for table_name, column_name in _COLUMN_CHANGES:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE NUMERIC(12, 2) '
                f'USING "{column_name}"::NUMERIC(12, 2)'
            )
        )


def _upgrade_sqlite() -> None:
    for table_name, column_name in _COLUMN_CHANGES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(column_name, existing_type=sa.Numeric(12, 2), type_=sa.Integer())


def _downgrade_sqlite() -> None:
    for table_name, column_name in _COLUMN_CHANGES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(column_name, existing_type=sa.Integer(), type_=sa.Numeric(12, 2))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _upgrade_postgresql()
        return
    _upgrade_sqlite()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _downgrade_postgresql()
        return
    _downgrade_sqlite()

