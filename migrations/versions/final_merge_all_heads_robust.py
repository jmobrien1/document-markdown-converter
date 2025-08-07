"""Final robust merge of all migration heads for deployment

Revision ID: final_merge_all_heads_robust
Revises: 98d3682e3e56, add_gcs_path_simple
Create Date: 2025-08-07 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'final_merge_all_heads_robust'
down_revision = ('98d3682e3e56', 'add_gcs_path_simple')
branch_labels = None
depends_on = None


def upgrade():
    """Merge all divergent migration heads"""
    # This is a merge migration - no schema changes needed
    pass


def downgrade():
    """No downgrade needed for merge migration"""
    pass 