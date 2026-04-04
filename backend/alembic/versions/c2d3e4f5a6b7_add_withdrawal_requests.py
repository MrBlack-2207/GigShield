"""add_withdrawal_requests

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-04 22:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'rejected')",
            name="ck_withdrawal_requests_status",
        ),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.worker_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_withdrawal_requests_worker_id_created_at",
        "withdrawal_requests",
        ["worker_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawal_requests_worker_id_created_at", table_name="withdrawal_requests")
    op.drop_table("withdrawal_requests")
