"""add delivery_zones table and zone_id to orders

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_zones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("delivery_time_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_delivery_zones_name"), "delivery_zones", ["name"], unique=True)

    op.add_column(
        "orders",
        sa.Column(
            "zone_id",
            sa.Integer(),
            sa.ForeignKey("delivery_zones.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_orders_zone_id"), "orders", ["zone_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_zone_id"), table_name="orders")
    op.drop_column("orders", "zone_id")
    op.drop_index(op.f("ix_delivery_zones_name"), table_name="delivery_zones")
    op.drop_table("delivery_zones")
