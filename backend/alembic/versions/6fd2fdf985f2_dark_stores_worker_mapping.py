"""dark_stores_worker_mapping

Revision ID: 6fd2fdf985f2
Revises: 02c76db1be70
Create Date: 2026-04-04 15:30:00.000000
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "6fd2fdf985f2"
down_revision: Union[str, None] = "02c76db1be70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dark_stores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("zone_id", sa.String(length=10), nullable=False),
        sa.Column("location", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("platform IN ('zepto', 'blinkit')", name="ck_dark_stores_platform"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.zone_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("workers", sa.Column("external_worker_id", sa.String(length=100), nullable=True))
    op.add_column("workers", sa.Column("home_store_id", sa.String(length=36), nullable=True))

    conn = op.get_bind()

    # Normalize existing worker platform values to lowercase.
    conn.execute(sa.text("UPDATE workers SET platform = lower(btrim(platform)) WHERE platform IS NOT NULL"))

    # Default missing/invalid platform values to zepto (explicit backfill choice).
    conn.execute(
        sa.text(
            """
            UPDATE workers
            SET platform = 'zepto'
            WHERE platform IS NULL OR platform NOT IN ('zepto', 'blinkit')
            """
        )
    )

    zone_ids = [row[0] for row in conn.execute(sa.text("SELECT zone_id FROM zones")).fetchall()]
    for zone_id in zone_ids:
        for platform in ("zepto", "blinkit"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO dark_stores (id, name, platform, zone_id, location, created_at, updated_at)
                    VALUES (:id, :name, :platform, :zone_id, :location, now(), now())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": f"Default {platform.title()} Store {zone_id}",
                    "platform": platform,
                    "zone_id": zone_id,
                    "location": None,
                },
            )

    # Map workers to default dark store by existing zone + normalized platform.
    conn.execute(
        sa.text(
            """
            UPDATE workers w
            SET home_store_id = ds.id
            FROM dark_stores ds
            WHERE ds.zone_id = w.primary_zone_id
              AND ds.platform = w.platform
              AND w.home_store_id IS NULL
            """
        )
    )

    op.create_foreign_key(
        "fk_workers_home_store_id_dark_stores",
        "workers",
        "dark_stores",
        ["home_store_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_workers_platform",
        "workers",
        "platform IN ('zepto', 'blinkit')",
    )
    op.create_unique_constraint(
        "uq_workers_platform_external_worker_id",
        "workers",
        ["platform", "external_worker_id"],
    )

    op.alter_column("workers", "platform", existing_type=sa.VARCHAR(length=20), nullable=False)
    op.alter_column("workers", "home_store_id", existing_type=sa.VARCHAR(length=36), nullable=False)


def downgrade() -> None:
    op.alter_column("workers", "home_store_id", existing_type=sa.VARCHAR(length=36), nullable=True)
    op.alter_column("workers", "platform", existing_type=sa.VARCHAR(length=20), nullable=True)

    op.drop_constraint("uq_workers_platform_external_worker_id", "workers", type_="unique")
    op.drop_constraint("ck_workers_platform", "workers", type_="check")
    op.drop_constraint("fk_workers_home_store_id_dark_stores", "workers", type_="foreignkey")

    op.drop_column("workers", "home_store_id")
    op.drop_column("workers", "external_worker_id")
    op.drop_table("dark_stores")
