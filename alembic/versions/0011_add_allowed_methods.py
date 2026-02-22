"""add allowed_methods to menu_configuration

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('menu_configuration', sa.Column('allowed_methods', sa.String(length=20), nullable=False, server_default='both'))


def downgrade():
    op.drop_column('menu_configuration', 'allowed_methods')
