"""add pickup and delivery to delivery_mode enum

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-21

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL не поддерживает ALTER TYPE ... ADD VALUE внутри транзакции
    # поэтому выполняем вне транзакции через COMMIT beforehand.
    op.execute("COMMIT")
    op.execute("ALTER TYPE deliverymode ADD VALUE IF NOT EXISTS 'delivery'")
    op.execute("ALTER TYPE deliverymode ADD VALUE IF NOT EXISTS 'pickup'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значений из enum без пересоздания типа.
    # Для отката: убедитесь, что в таблице orders нет строк с delivery_mode IN ('delivery','pickup'),
    # затем вручную пересоздайте тип.
    pass
