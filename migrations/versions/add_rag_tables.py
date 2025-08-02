"""Add RAG tables for citation-backed Q&A

Revision ID: add_rag_tables
Revises: 4dfacf4ae44f
Create Date: 2025-08-01 21:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rag_tables'
down_revision = '4dfacf4ae44f'
branch_labels = None
depends_on = None


def upgrade():
    # Create rag_chunks table
    op.create_table('rag_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversion_id', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('start_token', sa.Integer(), nullable=False),
        sa.Column('end_token', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversion_id'], ['conversions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create rag_queries table
    op.create_table('rag_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversion_id', sa.Integer(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('citations', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversion_id'], ['conversions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop rag_queries table
    op.drop_table('rag_queries')
    
    # Drop rag_chunks table
    op.drop_table('rag_chunks') 