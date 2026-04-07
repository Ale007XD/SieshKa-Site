"""add delivery_fee_rub to orders

Revision ID: 0014_add_delivery_fee_rub
Revises: 0013_add_order_number
Create Date: 2026-04-07 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014_add_delivery_fee_rub'
down_revision = '0013_add_order_number'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем колонку delivery_fee_rub (nullable — старые заказы получат NULL)
    op.add_column(
        'orders',
        sa.Column('delivery_fee_rub', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('orders', 'delivery_fee_rub')
