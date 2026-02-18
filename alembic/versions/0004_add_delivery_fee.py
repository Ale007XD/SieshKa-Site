"""add_delivery_fee

Revision ID: 0004_add_delivery_fee
Revises: 0003_add_availability_rules
Create Date: 2026-02-18 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004_add_delivery_fee'
down_revision: Union[str, None] = '0003_add_availability_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add delivery_fee column to menu_configuration table
    op.add_column(
        'menu_configuration',
        sa.Column('delivery_fee', sa.Integer(), server_default='0', nullable=False)
    )


def downgrade() -> None:
    # Remove delivery_fee column from menu_configuration table
    op.drop_column('menu_configuration', 'delivery_fee')
