"""Add gcs_path field to Conversion model

Revision ID: add_gcs_path_simple
Revises: consolidate_schema_canonical
Create Date: 2025-08-01 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_gcs_path_simple'
down_revision = 'consolidate_schema_canonical'
branch_labels = None
depends_on = None


def upgrade():
    # Add gcs_path column to conversions table
    with op.batch_alter_table('conversions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gcs_path', sa.String(length=500), nullable=True))


def downgrade():
    # Remove gcs_path column from conversions table
    with op.batch_alter_table('conversions', schema=None) as batch_op:
        batch_op.drop_column('gcs_path') 