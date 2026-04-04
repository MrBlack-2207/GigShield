"""add_zone_zdi_logs

Revision ID: 9d3d2e4b8a61
Revises: 6fd2fdf985f2
Create Date: 2026-04-04 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d3d2e4b8a61"
down_revision: Union[str, None] = "6fd2fdf985f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zone_zdi_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("zone_id", sa.String(length=10), nullable=False),
        sa.Column("zdi_value", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.zone_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zone_zdi_logs_timestamp", "zone_zdi_logs", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_zone_zdi_logs_timestamp", table_name="zone_zdi_logs")
    op.drop_table("zone_zdi_logs")
