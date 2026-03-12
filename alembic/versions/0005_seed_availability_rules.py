"""seed_availability_rules

Revision ID: 0005_seed_availability_rules
Revises: 0004_add_delivery_fee
Create Date: 2026-02-18 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = '0005_seed_availability_rules'
down_revision: Union[str, None] = '0004_add_delivery_fee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Seed availability rules for all existing products.
    Default: ALLDAY availability, both delivery and pickup methods.
    """
    connection = op.get_bind()
    
    # Get all active product IDs
    result = connection.execute(text("SELECT id FROM products WHERE is_active = true"))
    product_ids = [row[0] for row in result.fetchall()]
    
    if not product_ids:
        return
    
    # Insert availability rules for each product
    # Note: Enum in DB uses lowercase values ('product', 'category') as defined in migration 0003
    for product_id in product_ids:
        connection.execute(
            text("""
                INSERT INTO availability_rules 
                    (scope_type, scope_id, daypart, methods, is_active, created_at, updated_at)
                VALUES 
                    ('product', :product_id, 'ALLDAY', ARRAY['delivery', 'pickup'], true, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """),
            {"product_id": product_id}
        )


def downgrade() -> None:
    """
    Remove all product-scoped availability rules.
    """
    connection = op.get_bind()
    connection.execute(
        text("DELETE FROM availability_rules WHERE scope_type = 'product'")
    )

