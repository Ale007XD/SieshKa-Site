"""add_product_id_foreign_key

Revision ID: 0008_add_product_id_foreign_key
Revises: 0007_create_missing_rules
Create Date: 2026-02-20 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = '0008_add_product_id_foreign_key'
down_revision: Union[str, None] = '0007_create_missing_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add foreign key constraint to order_items.product_id referencing products.id.
    Set product_id to nullable with ON DELETE SET NULL.
    """
    connection = op.get_bind()
    
    # Check if column already has foreign key
    result = connection.execute(text("""
        SELECT COUNT(*) 
        FROM information_schema.table_constraints 
        WHERE constraint_name = 'order_items_product_id_fkey'
        AND table_name = 'order_items'
    """))
    
    if result.scalar() > 0:
        return
    
    # First, make product_id nullable (if not already)
    try:
        op.alter_column('order_items', 'product_id',
                       existing_type=sa.Integer(),
                       nullable=True)
    except Exception as e:
        pass
    
    # Clean up stale product_id references BEFORE adding constraint
    connection.execute(text("""
        UPDATE order_items
        SET product_id = NULL
        WHERE product_id IS NOT NULL
          AND product_id NOT IN (SELECT id FROM products)
    """))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'order_items_product_id_fkey',
        'order_items',
        'products',
        ['product_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """
    Remove foreign key constraint from order_items.product_id.
    """
    op.drop_constraint('order_items_product_id_fkey', 'order_items', type_='foreignkey')
