"""add max_orders_per_slot to menu_configuration

Revision ID: 0016_add_max_orders_per_slot
Revises: 0015_availability_rule
Create Date: 2026-04-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0016_add_max_orders_per_slot"
down_revision = "0015_availability_rule"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "menu_configuration",
        sa.Column(
            "max_orders_per_slot",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
    )


def downgrade():
    op.drop_column("menu_configuration", "max_orders_per_slot")
