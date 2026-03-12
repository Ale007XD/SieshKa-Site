"""fix_order_items_foreign_key

Revision ID: 0009_fix_order_items
Revises: 0008_add_product_id_foreign_key
Create Date: 2026-02-18

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0009_fix_order_items'
down_revision: Union[str, None] = '0008_add_product_id_foreign_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix foreign key constraint for order_items.product_id by cleaning up stale references.
    """
    from sqlalchemy import text
    connection = op.get_bind()
    
    # Clean up stale product_id references BEFORE adding constraint
    connection.execute(text("""
        UPDATE order_items
        SET product_id = NULL
        WHERE product_id IS NOT NULL
          AND product_id NOT IN (SELECT id FROM products)
    """))


def downgrade() -> None:
    """
    No downgrade needed for data cleanup.
    """
    pass
