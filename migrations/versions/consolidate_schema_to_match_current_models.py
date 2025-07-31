"""Consolidate schema to match current models

Revision ID: consolidate_schema_to_match_current_models
Revises: add_missing_subscription_columns
Create Date: 2025-07-31 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime, timezone
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'consolidate_schema_to_match_current_models'
down_revision = 'add_missing_subscription_columns'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def upgrade():
    """Create complete schema from scratch to match current models."""
    
    # Create users table with all required columns and constraints
    if not table_exists('users'):
        op.create_table('users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=False),
            sa.Column('password_hash', sa.String(length=128), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
            sa.Column('is_premium', sa.Boolean(), nullable=True, server_default=sa.text('false')),
            sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('premium_expires', sa.DateTime(), nullable=True),
            sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
            sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
            sa.Column('api_key', sa.String(length=64), nullable=True),
            sa.Column('subscription_status', sa.String(length=50), nullable=True, server_default=sa.text("'trial'")),
            sa.Column('current_tier', sa.String(length=50), nullable=True, server_default=sa.text("'free'")),
            sa.Column('subscription_start_date', sa.DateTime(), nullable=True),
            sa.Column('last_payment_date', sa.DateTime(), nullable=True),
            sa.Column('next_payment_date', sa.DateTime(), nullable=True),
            sa.Column('trial_start_date', sa.DateTime(), nullable=True),
            sa.Column('trial_end_date', sa.DateTime(), nullable=True),
            sa.Column('on_trial', sa.Boolean(), nullable=True, server_default=sa.text('true')),
            sa.Column('pro_pages_processed_current_month', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email'),
            sa.UniqueConstraint('stripe_customer_id'),
            sa.UniqueConstraint('stripe_subscription_id'),
            sa.UniqueConstraint('api_key')
        )
        
        # Create indexes for users table
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
            batch_op.create_index(batch_op.f('ix_users_api_key'), ['api_key'], unique=True)
    
    # Create anonymous_usage table
    if not table_exists('anonymous_usage'):
        op.create_table('anonymous_usage',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('conversions_today', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.Column('last_conversion', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create index for anonymous_usage table
        with op.batch_alter_table('anonymous_usage', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_anonymous_usage_session_id'), ['session_id'], unique=False)
    
    # Create conversions table
    if not table_exists('conversions'):
        op.create_table('conversions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('session_id', sa.String(length=64), nullable=True),
            sa.Column('original_filename', sa.String(length=255), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('file_type', sa.String(length=10), nullable=True),
            sa.Column('conversion_type', sa.String(length=20), nullable=True, server_default=sa.text("'standard'")),
            sa.Column('status', sa.String(length=20), nullable=True, server_default=sa.text("'pending'")),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('job_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('processing_time', sa.Float(), nullable=True),
            sa.Column('markdown_length', sa.Integer(), nullable=True),
            sa.Column('pages_processed', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create subscriptions table
    if not table_exists('subscriptions'):
        op.create_table('subscriptions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('stripe_subscription_id', sa.String(length=255), nullable=False),
            sa.Column('stripe_customer_id', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('tier', sa.String(length=50), nullable=False),
            sa.Column('current_period_start', sa.DateTime(), nullable=False),
            sa.Column('current_period_end', sa.DateTime(), nullable=False),
            sa.Column('trial_end', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('stripe_subscription_id')
        )
    
    # Create invoices table
    if not table_exists('invoices'):
        op.create_table('invoices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('subscription_id', sa.Integer(), nullable=False),
            sa.Column('stripe_invoice_id', sa.String(length=255), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=3), nullable=True, server_default=sa.text("'usd'")),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('stripe_invoice_id')
        )
    
    # Create batches table
    if not table_exists('batches'):
        op.create_table('batches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('batch_id', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=True, server_default=sa.text("'queued'")),
            sa.Column('total_files', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.Column('processed_files', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.Column('failed_files', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('batch_id')
        )
    
    # Create conversion_jobs table
    if not table_exists('conversion_jobs'):
        op.create_table('conversion_jobs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('batch_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('original_filename', sa.String(length=255), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('file_type', sa.String(length=10), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=True, server_default=sa.text("'queued'")),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('job_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('processing_time', sa.Float(), nullable=True),
            sa.Column('markdown_content', sa.Text(), nullable=True),
            sa.Column('markdown_length', sa.Integer(), nullable=True),
            sa.Column('pages_processed', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    """Remove all tables created by this migration."""
    # Drop tables in reverse order of creation (respecting foreign key constraints)
    if table_exists('conversion_jobs'):
        op.drop_table('conversion_jobs')
    
    if table_exists('batches'):
        op.drop_table('batches')
    
    if table_exists('invoices'):
        op.drop_table('invoices')
    
    if table_exists('subscriptions'):
        op.drop_table('subscriptions')
    
    if table_exists('conversions'):
        op.drop_table('conversions')
    
    if table_exists('anonymous_usage'):
        with op.batch_alter_table('anonymous_usage', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_anonymous_usage_session_id'))
        op.drop_table('anonymous_usage')
    
    if table_exists('users'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_users_api_key'))
            batch_op.drop_index(batch_op.f('ix_users_email'))
        op.drop_table('users') 