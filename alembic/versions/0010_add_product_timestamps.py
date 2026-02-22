"""add_created_at_updated_at_to_product

Revision ID: 0010_add_product_timestamps
Revises: 0009_fix_order_items
Create Date: 2026-02-22

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0010_add_product_timestamps'
down_revision: Union[str, None] = '0009_fix_order_items'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    op.add_column('products', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'updated_at')
    op.drop_column('products', 'created_at')
