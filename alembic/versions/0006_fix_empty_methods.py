"""fix_empty_methods

Revision ID: 0006_fix_empty_methods
Revises: 0005_seed_availability_rules
Create Date: 2026-02-19 06:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = '0006_fix_empty_methods'
down_revision: Union[str, None] = '0005_seed_availability_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix availability rules with empty methods array.
    Set default to ['delivery', 'pickup'] for rules with empty or NULL methods.
    """
    connection = op.get_bind()
    
    # Update rules with empty methods array or NULL
    result = connection.execute(
        text("""
            UPDATE availability_rules 
            SET methods = ARRAY['delivery', 'pickup']
            WHERE methods IS NULL OR array_length(methods, 1) IS NULL OR methods = '{}'
        """)
    )
    
    print(f"Fixed availability rules with empty methods")


def downgrade() -> None:
    """
    No downgrade needed - we don't want to revert valid data.
    """
    pass
