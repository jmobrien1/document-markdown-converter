"""Comprehensive merge of all migration heads for deployment

Revision ID: 98d3682e3e56
Revises: 0da239dd4a7a, add_gcs_path_simple
Create Date: 2025-08-07 10:18:30.915533

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '98d3682e3e56'
down_revision = ('0da239dd4a7a', 'add_gcs_path_simple')
branch_labels = None
depends_on = None


def upgrade():
    """Merge all divergent migration heads"""
    # This is a merge migration - no schema changes needed
    pass


def downgrade():
    """No downgrade needed for merge migration"""
    pass
