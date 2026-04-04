"""policy_tenure_weekly_billing

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-04-05 00:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("policies", sa.Column("tenure_months", sa.Integer(), nullable=True))
    op.add_column("policies", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policies", sa.Column("end_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policies", sa.Column("billing_cycle", sa.String(length=20), nullable=True))
    op.add_column("policies", sa.Column("last_premium_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policies", sa.Column("next_premium_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policies", sa.Column("cooldown_ends_at", sa.DateTime(timezone=True), nullable=True))

    op.alter_column(
        "policies",
        "status",
        existing_type=sa.VARCHAR(length=15),
        type_=sa.String(length=25),
        existing_nullable=True,
    )

    conn = op.get_bind()

    conn.execute(sa.text("UPDATE policies SET tenure_months = 1 WHERE tenure_months IS NULL"))
    conn.execute(sa.text("UPDATE policies SET start_date = COALESCE(created_at, now()) WHERE start_date IS NULL"))
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET end_date = start_date + (tenure_months || ' months')::interval
            WHERE end_date IS NULL
            """
        )
    )
    conn.execute(sa.text("UPDATE policies SET billing_cycle = 'weekly' WHERE billing_cycle IS NULL"))
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET last_premium_paid_at = COALESCE(created_at, start_date, now())
            WHERE last_premium_paid_at IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET next_premium_due_at = last_premium_paid_at + interval '7 days'
            WHERE next_premium_due_at IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET cooldown_ends_at = start_date + interval '48 hours'
            WHERE cooldown_ends_at IS NULL
            """
        )
    )

    conn.execute(sa.text("UPDATE policies SET status = lower(status) WHERE status IS NOT NULL"))
    conn.execute(sa.text("UPDATE policies SET status = 'active' WHERE status IS NULL"))
    conn.execute(sa.text("UPDATE policies SET status = 'inactive' WHERE status = 'suspended'"))
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET status = 'inactive'
            WHERE status NOT IN ('pending_activation', 'active', 'inactive', 'expired', 'cancelled')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET status = 'expired'
            WHERE status <> 'cancelled' AND end_date <= now()
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET status = 'inactive'
            WHERE status NOT IN ('cancelled', 'expired') AND next_premium_due_at < now()
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE policies
            SET status = 'pending_activation'
            WHERE status = 'active' AND cooldown_ends_at > now()
            """
        )
    )

    op.alter_column("policies", "tenure_months", existing_type=sa.Integer(), nullable=False)
    op.alter_column("policies", "start_date", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("policies", "end_date", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("policies", "billing_cycle", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("policies", "last_premium_paid_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("policies", "next_premium_due_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("policies", "cooldown_ends_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column(
        "policies",
        "status",
        existing_type=sa.String(length=25),
        nullable=False,
        server_default="pending_activation",
    )

    op.create_check_constraint("ck_policies_tenure_months", "policies", "tenure_months IN (1, 3, 6, 12)")
    op.create_check_constraint("ck_policies_billing_cycle_weekly", "policies", "billing_cycle = 'weekly'")
    op.create_check_constraint(
        "ck_policies_status_lifecycle",
        "policies",
        "status IN ('pending_activation', 'active', 'inactive', 'expired', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_policies_status_lifecycle", "policies", type_="check")
    op.drop_constraint("ck_policies_billing_cycle_weekly", "policies", type_="check")
    op.drop_constraint("ck_policies_tenure_months", "policies", type_="check")

    op.alter_column(
        "policies",
        "status",
        existing_type=sa.String(length=25),
        type_=sa.String(length=15),
        existing_nullable=False,
        server_default=None,
    )

    op.drop_column("policies", "cooldown_ends_at")
    op.drop_column("policies", "next_premium_due_at")
    op.drop_column("policies", "last_premium_paid_at")
    op.drop_column("policies", "billing_cycle")
    op.drop_column("policies", "end_date")
    op.drop_column("policies", "start_date")
    op.drop_column("policies", "tenure_months")
