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
        print("No active products found, skipping seed")
        return
    
    # Insert availability rules for each product
    # Use uppercase for enum values to match PostgreSQL enum definition
    for product_id in product_ids:
        connection.execute(
            text("""
                INSERT INTO availability_rules 
                    (scope_type, scope_id, daypart, methods, is_active, created_at, updated_at)
                VALUES 
                    ('PRODUCT', :product_id, 'ALLDAY', ARRAY['delivery', 'pickup'], true, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """),
            {"product_id": product_id}
        )
    
    print(f"Created availability rules for {len(product_ids)} products")


def downgrade() -> None:
    """
    Remove all product-scoped availability rules.
    """
    connection = op.get_bind()
    # Delete both uppercase and lowercase versions for compatibility
    connection.execute(
        text("DELETE FROM availability_rules WHERE scope_type = 'PRODUCT' OR scope_type = 'product'")
    )
    print("Removed all product availability rules")
