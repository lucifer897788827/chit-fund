from alembic import op
import sqlalchemy as sa


revision = "20260421_0006"
down_revision = "20260421_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "membership_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("slot_number", sa.Integer(), nullable=False),
        sa.Column("has_won", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["chit_groups.id"]),
        sa.UniqueConstraint("group_id", "slot_number"),
    )
    op.create_index("ix_membership_slots_user_id", "membership_slots", ["user_id"], unique=False)
    op.create_index("ix_membership_slots_group_id", "membership_slots", ["group_id"], unique=False)
    op.create_index(
        "ix_membership_slots_group_user_has_won",
        "membership_slots",
        ["group_id", "user_id", "has_won"],
        unique=False,
    )

    connection = op.get_bind()
    group_memberships = sa.table(
        "group_memberships",
        sa.column("group_id", sa.Integer()),
        sa.column("subscriber_id", sa.Integer()),
        sa.column("member_no", sa.Integer()),
        sa.column("prized_status", sa.String(length=30)),
    )
    subscribers = sa.table(
        "subscribers",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
    )
    membership_slots = sa.table(
        "membership_slots",
        sa.column("user_id", sa.Integer()),
        sa.column("group_id", sa.Integer()),
        sa.column("slot_number", sa.Integer()),
        sa.column("has_won", sa.Boolean()),
    )

    existing_memberships = connection.execute(
        sa.select(
            subscribers.c.user_id,
            group_memberships.c.group_id,
            group_memberships.c.member_no,
            group_memberships.c.prized_status,
        ).select_from(
            group_memberships.join(subscribers, subscribers.c.id == group_memberships.c.subscriber_id)
        )
    ).all()

    if existing_memberships:
        connection.execute(
            membership_slots.insert(),
            [
                {
                    "user_id": row.user_id,
                    "group_id": row.group_id,
                    "slot_number": row.member_no,
                    "has_won": row.prized_status == "prized",
                }
                for row in existing_memberships
            ],
        )

def downgrade():
    op.drop_index("ix_membership_slots_group_user_has_won", table_name="membership_slots")
    op.drop_index("ix_membership_slots_group_id", table_name="membership_slots")
    op.drop_index("ix_membership_slots_user_id", table_name="membership_slots")
    op.drop_table("membership_slots")
