"""Merge multiple migration heads

Revision ID: 0da239dd4a7a
Revises: initial_migration_001
Create Date: 2025-08-07 09:53:48.409904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0da239dd4a7a'
down_revision = 'initial_migration_001'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
