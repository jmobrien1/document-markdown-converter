"""Initial migration with RAG chunks table

Revision ID: initial_migration_001
Revises: 
Create Date: 2025-08-05 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'initial_migration_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create initial tables including RAG chunks"""
    # Create rag_chunks table with correct schema
    op.create_table('rag_chunks',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['conversions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    """Drop all tables"""
    op.drop_table('rag_chunks') 