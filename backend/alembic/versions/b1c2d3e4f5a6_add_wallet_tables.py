"""add_wallet_tables

Revision ID: b1c2d3e4f5a6
Revises: 9d3d2e4b8a61
Create Date: 2026-04-04 22:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "9d3d2e4b8a61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=36), nullable=False),
        sa.Column("balance", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.worker_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="uq_wallets_worker_id"),
    )

    op.create_table(
        "wallet_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "type IN ('payout', 'withdrawal', 'premium', 'adjustment')",
            name="ck_wallet_ledger_entries_type",
        ),
        sa.CheckConstraint(
            "(type = 'adjustment') OR (reference_id IS NOT NULL)",
            name="ck_wallet_ledger_entries_reference_required",
        ),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "wallet_id",
            "type",
            "reference_id",
            name="uq_wallet_ledger_wallet_type_reference",
        ),
    )

    op.create_index(
        "ix_wallet_ledger_entries_wallet_id_created_at",
        "wallet_ledger_entries",
        ["wallet_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_ledger_entries_wallet_id_created_at", table_name="wallet_ledger_entries")
    op.drop_table("wallet_ledger_entries")
    op.drop_table("wallets")
