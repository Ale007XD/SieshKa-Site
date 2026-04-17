"""add max_message_ids and max_message_text to orders

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017_add_client_max_uid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("max_message_ids", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("max_message_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "max_message_text")
    op.drop_column("orders", "max_message_ids")
