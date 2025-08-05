"""Fix RAG schema auto-increment and column types

Revision ID: fix_rag_auto_increment_003
Revises: fix_rag_schema_002
Create Date: 2025-08-05 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fix_rag_auto_increment_003'
down_revision = 'fix_rag_schema_002'
branch_labels = None
depends_on = None


def upgrade():
    """Fix RAG schema to use auto-incrementing IDs and proper column types"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if inspector.has_table('rag_chunks'):
        # Check current column types
        columns = inspector.get_columns('rag_chunks')
        id_col = next((col for col in columns if col['name'] == 'id'), None)
        document_id_col = next((col for col in columns if col['name'] == 'document_id'), None)
        embedding_col = next((col for col in columns if col['name'] == 'embedding'), None)
        
        # Fix id column to be SERIAL if it's not already
        if id_col and id_col['type'].__class__.__name__ != 'INTEGER':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN id TYPE INTEGER,
                ALTER COLUMN id SET DEFAULT nextval('rag_chunks_id_seq')
            """)
        
        # Fix document_id column to be INTEGER if it's not already
        if document_id_col and document_id_col['type'].__class__.__name__ != 'INTEGER':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN document_id TYPE INTEGER
            """)
        
        # Fix embedding column to be JSON if it's not already
        if embedding_col and embedding_col['type'].__class__.__name__ != 'JSON':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN embedding TYPE JSON USING embedding::json
            """)
    
    # Ensure sequence exists for auto-increment
    op.execute("""
        CREATE SEQUENCE IF NOT EXISTS rag_chunks_id_seq;
        ALTER TABLE rag_chunks ALTER COLUMN id SET DEFAULT nextval('rag_chunks_id_seq');
    """)


def downgrade():
    """Revert changes if needed"""
    # This is a schema fix - downgrade not implemented
    pass 