"""feat(db): Consolidate schema to match current models and ensure idempotency

Revision ID: consolidate_schema_canonical
Revises: 8ddbcc4fa19d
Create Date: 2025-07-31 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'consolidate_schema_canonical'
down_revision = '8ddbcc4fa19d'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def upgrade():
    """Upgrade to canonical schema."""
    
    # Create users table
    if not table_exists('users'):
        op.create_table('users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=False),
            sa.Column('password_hash', sa.String(length=128), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('is_premium', sa.Boolean(), nullable=True),
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('premium_expires', sa.DateTime(), nullable=True),
            sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
            sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
            sa.Column('api_key', sa.String(length=64), nullable=True),
            sa.Column('subscription_status', sa.String(length=50), nullable=True),
            sa.Column('current_tier', sa.String(length=50), nullable=True),
            sa.Column('subscription_start_date', sa.DateTime(), nullable=True),
            sa.Column('last_payment_date', sa.DateTime(), nullable=True),
            sa.Column('next_payment_date', sa.DateTime(), nullable=True),
            sa.Column('trial_start_date', sa.DateTime(), nullable=True),
            sa.Column('trial_end_date', sa.DateTime(), nullable=True),
            sa.Column('on_trial', sa.Boolean(), nullable=True),
            sa.Column('pro_pages_processed_current_month', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
        op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)
        op.create_index(op.f('ix_users_stripe_customer_id'), 'users', ['stripe_customer_id'], unique=True)
        op.create_index(op.f('ix_users_stripe_subscription_id'), 'users', ['stripe_subscription_id'], unique=True)
    
    # Add missing columns to users table if they don't exist
    if table_exists('users'):
        if not column_exists('users', 'subscription_status'):
            op.add_column('users', sa.Column('subscription_status', sa.String(length=50), nullable=True))
        if not column_exists('users', 'current_tier'):
            op.add_column('users', sa.Column('current_tier', sa.String(length=50), nullable=True))
        if not column_exists('users', 'subscription_start_date'):
            op.add_column('users', sa.Column('subscription_start_date', sa.DateTime(), nullable=True))
        if not column_exists('users', 'last_payment_date'):
            op.add_column('users', sa.Column('last_payment_date', sa.DateTime(), nullable=True))
        if not column_exists('users', 'next_payment_date'):
            op.add_column('users', sa.Column('next_payment_date', sa.DateTime(), nullable=True))
        if not column_exists('users', 'trial_start_date'):
            op.add_column('users', sa.Column('trial_start_date', sa.DateTime(), nullable=True))
        if not column_exists('users', 'trial_end_date'):
            op.add_column('users', sa.Column('trial_end_date', sa.DateTime(), nullable=True))
        if not column_exists('users', 'on_trial'):
            op.add_column('users', sa.Column('on_trial', sa.Boolean(), nullable=True))
        if not column_exists('users', 'pro_pages_processed_current_month'):
            op.add_column('users', sa.Column('pro_pages_processed_current_month', sa.Integer(), nullable=True))
        if not column_exists('users', 'api_key'):
            op.add_column('users', sa.Column('api_key', sa.String(length=64), nullable=True))
            op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)
        if not column_exists('users', 'is_admin'):
            op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Create teams table
    if not table_exists('teams'):
        op.create_table('teams',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create team_members table
    if not table_exists('team_members'):
        op.create_table('team_members',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('team_id', sa.Integer(), nullable=False),
            sa.Column('role', sa.String(length=50), nullable=False),
            sa.Column('joined_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'team_id', name='uq_user_team')
        )
    
    # Create conversions table
    if not table_exists('conversions'):
        op.create_table('conversions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('session_id', sa.String(length=64), nullable=True),
            sa.Column('original_filename', sa.String(length=255), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('file_type', sa.String(length=10), nullable=True),
            sa.Column('conversion_type', sa.String(length=20), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('job_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('processing_time', sa.Float(), nullable=True),
            sa.Column('markdown_length', sa.Integer(), nullable=True),
            sa.Column('pages_processed', sa.Integer(), nullable=True),
            sa.Column('structured_data', sqlite.JSON, nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Add missing columns to conversions table if they don't exist
    if table_exists('conversions'):
        if not column_exists('conversions', 'job_id'):
            op.add_column('conversions', sa.Column('job_id', sa.String(length=64), nullable=True))
        if not column_exists('conversions', 'pages_processed'):
            op.add_column('conversions', sa.Column('pages_processed', sa.Integer(), nullable=True))
        if not column_exists('conversions', 'structured_data'):
            op.add_column('conversions', sa.Column('structured_data', sqlite.JSON, nullable=True))
    
    # Create anonymous_usage table
    if not table_exists('anonymous_usage'):
        op.create_table('anonymous_usage',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('conversions_today', sa.Integer(), nullable=True),
            sa.Column('last_conversion', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_anonymous_usage_session_id'), 'anonymous_usage', ['session_id'], unique=False)
    
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
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('stripe_subscription_id', name='uq_subscription_stripe_id')
        )
    
    # Create invoices table
    if not table_exists('invoices'):
        op.create_table('invoices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('subscription_id', sa.Integer(), nullable=False),
            sa.Column('stripe_invoice_id', sa.String(length=255), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=3), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('stripe_invoice_id', name='uq_invoice_stripe_id')
        )
    
    # Create batches table
    if not table_exists('batches'):
        op.create_table('batches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('batch_id', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=True),
            sa.Column('total_files', sa.Integer(), nullable=True),
            sa.Column('processed_files', sa.Integer(), nullable=True),
            sa.Column('failed_files', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('batch_id', name='uq_batch_id')
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
            sa.Column('status', sa.String(length=50), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('job_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
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
    """Downgrade by dropping all tables."""
    op.drop_table('conversion_jobs')
    op.drop_table('batches')
    op.drop_table('invoices')
    op.drop_table('subscriptions')
    op.drop_table('anonymous_usage')
    op.drop_table('conversions')
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_table('users') 