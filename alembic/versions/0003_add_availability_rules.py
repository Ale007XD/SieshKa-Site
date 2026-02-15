"""add_availability_rules

Revision ID: 0003_add_availability_rules
Revises: 0002_add_category_parent_id
Create Date: 2026-02-15 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003_add_availability_rules'
down_revision: Union[str, None] = '0002_add_category_parent_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Availability Rules Table ###
    op.create_table(
        'availability_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.Enum('product', 'category', name='availabilityscopetype'), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=False),
        sa.Column('daypart', sa.Enum('MORNING', 'EVENING', 'ALLDAY', name='daypart'), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('lead_time_minutes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('methods', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('allow_tomorrow', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('tomorrow_cutoff', sa.Time(), server_default='23:00:00', nullable=False),
        sa.Column('timezone', sa.String(length=50), server_default='Asia/Ho_Chi_Minh', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for availability_rules
    op.create_index('ix_availability_rules_scope', 'availability_rules', ['scope_type', 'scope_id'], unique=False)
    op.create_index('ix_availability_rules_active', 'availability_rules', ['is_active'], unique=False)
    
    # ### Cart Drafts Table ###
    op.create_table(
        'cart_drafts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cart_key', sa.String(length=64), nullable=False),
        sa.Column('customer_name', sa.String(length=120), nullable=True),
        sa.Column('phone_e164', sa.String(length=32), nullable=True),
        sa.Column('target_day', sa.String(length=10), nullable=False),
        sa.Column('delivery_method', sa.String(length=20), nullable=False),
        sa.Column('selected_slot', sa.String(length=20), nullable=True),
        sa.Column('items_json', sa.Text(), nullable=False),
        sa.Column('total_rub', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cart_key')
    )
    
    op.create_index('ix_cart_drafts_cart_key', 'cart_drafts', ['cart_key'], unique=True)
    op.create_index('ix_cart_drafts_expires', 'cart_drafts', ['expires_at'], unique=False)
    
    # ### Menu Configuration Table ###
    op.create_table(
        'menu_configuration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_tz', sa.String(length=50), server_default='Asia/Ho_Chi_Minh', nullable=False),
        sa.Column('morning_start', sa.Time(), server_default='07:00:00', nullable=False),
        sa.Column('morning_end', sa.Time(), server_default='10:00:00', nullable=False),
        sa.Column('evening_start', sa.Time(), server_default='14:00:00', nullable=False),
        sa.Column('evening_end', sa.Time(), server_default='21:00:00', nullable=False),
        sa.Column('slot_interval_minutes', sa.Integer(), server_default='15', nullable=False),
        sa.Column('base_buffer_minutes', sa.Integer(), server_default='15', nullable=False),
        sa.Column('enable_tomorrow_orders', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('tomorrow_order_cutoff', sa.Time(), server_default='23:00:00', nullable=False),
        sa.Column('menu_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert default menu configuration
    op.execute("""
        INSERT INTO menu_configuration (id) VALUES (1)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_cart_drafts_expires', table_name='cart_drafts')
    op.drop_index('ix_cart_drafts_cart_key', table_name='cart_drafts')
    op.drop_index('ix_availability_rules_active', table_name='availability_rules')
    op.drop_index('ix_availability_rules_scope', table_name='availability_rules')
    
    # Drop tables
    op.drop_table('menu_configuration')
    op.drop_table('cart_drafts')
    op.drop_table('availability_rules')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS daypart')
    op.execute('DROP TYPE IF EXISTS availabilityscopetype')
