"""create availability_rule table

Revision ID: 0015_availability_rule
Revises: 0014_add_delivery_fee_rub
Create Date: 2026-04-07 18:54:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0015_availability_rule'
down_revision = '0014_add_delivery_fee_rub'
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу availability_rule
    op.create_table(
        'availability_rule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=20), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=False),
        sa.Column('daypart', sa.String(length=20), nullable=True),
        sa.Column('lead_time_minutes', sa.Integer(), nullable=True),
        sa.Column('methods', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('allow_tomorrow', sa.Boolean(), nullable=True),
        sa.Column('tomorrow_cutoff', sa.Time(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("scope_type IN ('product', 'category')", name='check_scope_type')
    )
    
    # Базовые правила для категорий из меню (Салаты=17, Закуски=22, Горячее=21)
    op.execute("""
        INSERT INTO availability_rule 
        (scope_type, scope_id, daypart, lead_time_minutes, methods, allow_tomorrow, is_active, created_at)
        VALUES 
            ('category', 17, 'EVENING', 45, ARRAY['delivery'], true, true, NOW()),
            ('category', 22, 'EVENING', 30, ARRAY['delivery'], true, true, NOW()),
            ('category', 21, 'EVENING', 60, ARRAY['delivery'], true, true, NOW()),
            ('category', 20, 'EVENING', 20, ARRAY['delivery'], true, true, NOW()),
            ('category', 4,  'ALLDAY',  0,  ARRAY['delivery'], true, true, NOW())
        ON CONFLICT DO NOTHING;
    """)


def downgrade():
    op.drop_table('availability_rule')
