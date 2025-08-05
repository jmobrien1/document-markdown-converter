"""Merge multiple migration heads

Revision ID: 74d523f5639b
Revises: add_gcs_path_column, add_rag_tables, consolidate_schema_canonical
Create Date: 2025-08-04 19:38:12.851151

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '74d523f5639b'
down_revision = ('add_gcs_path_column', 'add_rag_tables', 'consolidate_schema_canonical')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
