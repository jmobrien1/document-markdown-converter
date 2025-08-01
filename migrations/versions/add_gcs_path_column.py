"""Add gcs_path column to conversions table

Revision ID: add_gcs_path_column
Revises: consolidate_schema_canonical
Create Date: 2025-08-01 10:18:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_gcs_path_column'
down_revision = '4dfacf4ae44f'
branch_labels = None
depends_on = None


def upgrade():
    # Add gcs_path column to conversions table
    op.add_column('conversions', sa.Column('gcs_path', sa.String(length=500), nullable=True))


def downgrade():
    # Remove gcs_path column from conversions table
    op.drop_column('conversions', 'gcs_path') 