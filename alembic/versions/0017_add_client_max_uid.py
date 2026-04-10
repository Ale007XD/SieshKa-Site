"""add client_max_uid to orders

Revision ID: 0017_add_client_max_uid
Revises: 0016_add_max_orders_per_slot
Create Date: 2026-04-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0017_add_client_max_uid"
down_revision = "0016_add_max_orders_per_slot"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("client_max_uid", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_orders_client_max_uid", "orders", ["client_max_uid"])


def downgrade():
    op.drop_index("ix_orders_client_max_uid", table_name="orders")
    op.drop_column("orders", "client_max_uid")
