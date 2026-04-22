from alembic import op
import sqlalchemy as sa


revision = "20260415_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=False)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.create_table(
        "owners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address_text", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_subscribers_phone"), "subscribers", ["phone"], unique=False)

    op.create_table(
        "chit_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("group_code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("chit_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("installment_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("cycle_count", sa.Integer(), nullable=False),
        sa.Column("cycle_frequency", sa.String(length=30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("first_auction_date", sa.Date(), nullable=False),
        sa.Column("current_cycle_no", sa.Integer(), nullable=False),
        sa.Column("bidding_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.UniqueConstraint("owner_id", "group_code"),
    )
    op.create_index(op.f("ix_chit_groups_owner_id"), "chit_groups", ["owner_id"], unique=False)

    op.create_table(
        "group_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("member_no", sa.Integer(), nullable=False),
        sa.Column("membership_status", sa.String(length=30), nullable=False),
        sa.Column("prized_status", sa.String(length=30), nullable=False),
        sa.Column("prized_cycle_no", sa.Integer(), nullable=True),
        sa.Column("can_bid", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.UniqueConstraint("group_id", "member_no"),
        sa.UniqueConstraint("group_id", "subscriber_id"),
    )
    op.create_index(op.f("ix_group_memberships_group_id"), "group_memberships", ["group_id"], unique=False)
    op.create_index(op.f("ix_group_memberships_subscriber_id"), "group_memberships", ["subscriber_id"], unique=False)

    op.create_table(
        "installments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("due_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("penalty_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("balance_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["group_memberships.id"]),
        sa.UniqueConstraint("group_id", "membership_id", "cycle_no"),
    )
    op.create_index(op.f("ix_installments_group_id"), "installments", ["group_id"], unique=False)
    op.create_index(op.f("ix_installments_membership_id"), "installments", ["membership_id"], unique=False)

    op.create_table(
        "auction_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bidding_window_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("winning_bid_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_auction_sessions_group_id"), "auction_sessions", ["group_id"], unique=False)

    op.create_table(
        "auction_bids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auction_session_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("bidder_user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("bid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("bid_discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("invalid_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_bid_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["auction_session_id"], ["auction_sessions.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["group_memberships.id"]),
        sa.ForeignKeyConstraint(["bidder_user_id"], ["users.id"]),
        sa.UniqueConstraint("auction_session_id", "bidder_user_id", "idempotency_key"),
    )
    op.create_index(op.f("ix_auction_bids_auction_session_id"), "auction_bids", ["auction_session_id"], unique=False)
    op.create_index(op.f("ix_auction_bids_membership_id"), "auction_bids", ["membership_id"], unique=False)
    op.create_index(op.f("ix_auction_bids_bidder_user_id"), "auction_bids", ["bidder_user_id"], unique=False)

    op.create_table(
        "auction_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auction_session_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=False),
        sa.Column("winner_membership_id", sa.Integer(), nullable=False),
        sa.Column("winning_bid_id", sa.Integer(), nullable=False),
        sa.Column("winning_bid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("dividend_pool_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("dividend_per_member_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("owner_commission_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("winner_payout_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auction_session_id"], ["auction_sessions.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.ForeignKeyConstraint(["winner_membership_id"], ["group_memberships.id"]),
        sa.ForeignKeyConstraint(["winning_bid_id"], ["auction_bids.id"]),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("auction_session_id"),
    )
    op.create_index(op.f("ix_auction_results_group_id"), "auction_results", ["group_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("installment_id", sa.Integer(), nullable=True),
        sa.Column("payment_type", sa.String(length=30), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["group_memberships.id"]),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_payments_owner_id"), "payments", ["owner_id"], unique=False)
    op.create_index(op.f("ix_payments_subscriber_id"), "payments", ["subscriber_id"], unique=False)

    op.create_table(
        "payouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("auction_result_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("deductions_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payout_method", sa.String(length=30), nullable=False),
        sa.Column("payout_date", sa.Date(), nullable=True),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.ForeignKeyConstraint(["auction_result_id"], ["auction_results.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["group_memberships.id"]),
        sa.UniqueConstraint("auction_result_id"),
    )
    op.create_index(op.f("ix_payouts_owner_id"), "payouts", ["owner_id"], unique=False)

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("source_table", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("credit_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
    )
    op.create_index(op.f("ix_ledger_entries_owner_id"), "ledger_entries", ["owner_id"], unique=False)

    op.create_table(
        "external_chits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("organizer_name", sa.String(length=255), nullable=False),
        sa.Column("chit_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("installment_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cycle_frequency", sa.String(length=30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
    )
    op.create_index(op.f("ix_external_chits_subscriber_id"), "external_chits", ["subscriber_id"], unique=False)

    op.create_table(
        "external_chit_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_chit_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["external_chit_id"], ["external_chits.id"]),
    )
    op.create_index(op.f("ix_external_chit_entries_external_chit_id"), "external_chit_entries", ["external_chit_id"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("metadata_json", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
    )


def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_external_chit_entries_external_chit_id"), table_name="external_chit_entries")
    op.drop_table("external_chit_entries")
    op.drop_index(op.f("ix_external_chits_subscriber_id"), table_name="external_chits")
    op.drop_table("external_chits")
    op.drop_index(op.f("ix_ledger_entries_owner_id"), table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index(op.f("ix_payouts_owner_id"), table_name="payouts")
    op.drop_table("payouts")
    op.drop_index(op.f("ix_payments_subscriber_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_owner_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_auction_results_group_id"), table_name="auction_results")
    op.drop_table("auction_results")
    op.drop_index(op.f("ix_auction_bids_bidder_user_id"), table_name="auction_bids")
    op.drop_index(op.f("ix_auction_bids_membership_id"), table_name="auction_bids")
    op.drop_index(op.f("ix_auction_bids_auction_session_id"), table_name="auction_bids")
    op.drop_table("auction_bids")
    op.drop_index(op.f("ix_auction_sessions_group_id"), table_name="auction_sessions")
    op.drop_table("auction_sessions")
    op.drop_index(op.f("ix_installments_membership_id"), table_name="installments")
    op.drop_index(op.f("ix_installments_group_id"), table_name="installments")
    op.drop_table("installments")
    op.drop_index(op.f("ix_group_memberships_subscriber_id"), table_name="group_memberships")
    op.drop_index(op.f("ix_group_memberships_group_id"), table_name="group_memberships")
    op.drop_table("group_memberships")
    op.drop_index(op.f("ix_chit_groups_owner_id"), table_name="chit_groups")
    op.drop_table("chit_groups")
    op.drop_index(op.f("ix_subscribers_phone"), table_name="subscribers")
    op.drop_table("subscribers")
    op.drop_table("owners")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_table("users")
