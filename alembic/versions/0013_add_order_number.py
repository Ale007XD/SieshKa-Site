"""add order_number to orders

Revision ID: 0013_add_order_number
Revises: 9c445de5fdf5
Create Date: 2026-04-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0013_add_order_number'
down_revision = '9c445de5fdf5'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем колонку order_number (nullable, чтобы старые заказы не сломались)
    op.add_column(
        'orders',
        sa.Column('order_number', sa.String(length=20), nullable=True)
    )
    op.create_index('ix_orders_order_number', 'orders', ['order_number'], unique=True)

    # Заполняем order_number для уже существующих заказов в формате ГГ-ММ-ДД-00N
    op.execute("""
        UPDATE orders
        SET order_number = (
            TO_CHAR(created_at, 'YY-MM-DD') || '-' ||
            LPAD(
                CAST(
                    ROW_NUMBER() OVER (
                        PARTITION BY DATE(created_at)
                        ORDER BY id
                    ) AS TEXT
                ),
                3, '0'
            )
        )
        WHERE order_number IS NULL
    """)


def downgrade():
    op.drop_index('ix_orders_order_number', table_name='orders')
    op.drop_column('orders', 'order_number')
