"""create_missing_availability_rules

Revision ID: 0007_create_missing_rules
Revises: 0006_fix_empty_methods
Create Date: 2026-02-19 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = '0007_create_missing_rules'
down_revision: Union[str, None] = '0006_fix_empty_methods'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create availability rules for products that don't have them.
    """
    connection = op.get_bind()
    
    # Find products without availability rules
    result = connection.execute(
        text("""
            SELECT p.id 
            FROM products p
            LEFT JOIN availability_rules ar ON ar.scope_type = 'product' AND ar.scope_id = p.id
            WHERE p.is_active = true AND ar.id IS NULL
        """)
    )
    
    product_ids = [row[0] for row in result.fetchall()]
    
    if not product_ids:
        return
    
    # Create rules for each product
    for product_id in product_ids:
        connection.execute(
            text("""
                INSERT INTO availability_rules 
                    (scope_type, scope_id, daypart, methods, lead_time_minutes, is_active, created_at, updated_at)
                VALUES 
                    ('product', :product_id, 'ALLDAY', ARRAY['delivery', 'pickup'], 0, true, NOW(), NOW())
            """),
            {"product_id": product_id}
        )


def downgrade() -> None:
    """
    No downgrade - we don't want to delete valid rules.
    """
    pass
