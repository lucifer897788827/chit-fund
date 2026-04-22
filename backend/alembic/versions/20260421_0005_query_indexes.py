from alembic import op


revision = "20260421_0005"
down_revision = "20260421_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_payments_owner_created_at_id",
        "payments",
        ["owner_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_payments_owner_payment_date_id",
        "payments",
        ["owner_id", "payment_date", "id"],
        unique=False,
    )
    op.create_index(
        "ix_payments_owner_subscriber_payment_date_id",
        "payments",
        ["owner_id", "subscriber_id", "payment_date", "id"],
        unique=False,
    )
    op.create_index(
        "ix_payouts_owner_created_at_id",
        "payouts",
        ["owner_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_payouts_owner_subscriber_created_at_id",
        "payouts",
        ["owner_id", "subscriber_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_auction_sessions_status_id",
        "auction_sessions",
        ["status", "id"],
        unique=False,
    )
    op.create_index(
        "ix_auction_sessions_group_created_at_id",
        "auction_sessions",
        ["group_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_auction_bids_session_valid_bid_amount_placed_at_id",
        "auction_bids",
        ["auction_session_id", "is_valid", "bid_amount", "placed_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_job_runs_status_started_at_id",
        "job_runs",
        ["status", "started_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_job_runs_task_name_status_started_at_id",
        "job_runs",
        ["task_name", "status", "started_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_job_runs_status_updated_at_id",
        "job_runs",
        ["status", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_user_owner_created_at_id",
        "notifications",
        ["user_id", "owner_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_status_id",
        "notifications",
        ["status", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_read_at_id",
        "notifications",
        ["read_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_group_memberships_group_id_membership_status",
        "group_memberships",
        ["group_id", "membership_status", "subscriber_id"],
        unique=False,
    )
    op.create_index(
        "ix_installments_group_id_status_due_date_id",
        "installments",
        ["group_id", "status", "due_date", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_installments_group_id_status_due_date_id", table_name="installments")
    op.drop_index("ix_group_memberships_group_id_membership_status", table_name="group_memberships")
    op.drop_index("ix_notifications_read_at_id", table_name="notifications")
    op.drop_index("ix_notifications_status_id", table_name="notifications")
    op.drop_index("ix_notifications_user_owner_created_at_id", table_name="notifications")
    op.drop_index("ix_job_runs_status_updated_at_id", table_name="job_runs")
    op.drop_index("ix_job_runs_task_name_status_started_at_id", table_name="job_runs")
    op.drop_index("ix_job_runs_status_started_at_id", table_name="job_runs")
    op.drop_index("ix_auction_bids_session_valid_bid_amount_placed_at_id", table_name="auction_bids")
    op.drop_index("ix_auction_sessions_group_created_at_id", table_name="auction_sessions")
    op.drop_index("ix_auction_sessions_status_id", table_name="auction_sessions")
    op.drop_index("ix_payouts_owner_subscriber_created_at_id", table_name="payouts")
    op.drop_index("ix_payouts_owner_created_at_id", table_name="payouts")
    op.drop_index("ix_payments_owner_subscriber_payment_date_id", table_name="payments")
    op.drop_index("ix_payments_owner_payment_date_id", table_name="payments")
    op.drop_index("ix_payments_owner_created_at_id", table_name="payments")
