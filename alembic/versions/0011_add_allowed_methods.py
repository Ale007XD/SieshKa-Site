"""add allowed_methods to menu_configuration

Revision ID: 0011_add_allowed_methods
Revises: 0010_add_product_timestamps
Create Date: 2026-02-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0011_add_allowed_methods'
down_revision = '0010_add_product_timestamps'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('menu_configuration', sa.Column('allowed_methods', sa.String(length=20), nullable=False, server_default='both'))


def downgrade():
    op.drop_column('menu_configuration', 'allowed_methods')
