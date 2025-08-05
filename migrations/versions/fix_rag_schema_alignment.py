"""Fix RAG schema alignment

Revision ID: fix_rag_schema_002
Revises: fix_rag_embedding_001
Create Date: 2025-08-05 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fix_rag_schema_002'
down_revision = 'fix_rag_embedding_001'
branch_labels = None
depends_on = None


def upgrade():
    """Fix RAG schema alignment issues"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if inspector.has_table('rag_chunks'):
        # Check current column types
        columns = inspector.get_columns('rag_chunks')
        document_id_col = next((col for col in columns if col['name'] == 'document_id'), None)
        embedding_col = next((col for col in columns if col['name'] == 'embedding'), None)
        
        # Fix document_id column type if needed
        if document_id_col and document_id_col['type'].__class__.__name__ == 'INTEGER':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN document_id TYPE VARCHAR(36) USING document_id::VARCHAR(36)
            """)
            print("✅ Changed rag_chunks.document_id from INTEGER to VARCHAR(36)")
        
        # Fix embedding column type if needed
        if embedding_col and embedding_col['type'].__class__.__name__ == 'LargeBinary':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN embedding TYPE JSON USING NULL
            """)
            print("✅ Changed rag_chunks.embedding from LargeBinary to JSON")
        
        # Fix id column type if needed
        id_col = next((col for col in columns if col['name'] == 'id'), None)
        if id_col and id_col['type'].__class__.__name__ == 'VARCHAR':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN id TYPE SERIAL
            """)
            print("✅ Changed rag_chunks.id from VARCHAR to SERIAL")
    else:
        print("ℹ️ rag_chunks table doesn't exist yet")


def downgrade():
    """Revert schema changes (if needed)"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if inspector.has_table('rag_chunks'):
        columns = inspector.get_columns('rag_chunks')
        document_id_col = next((col for col in columns if col['name'] == 'document_id'), None)
        embedding_col = next((col for col in columns if col['name'] == 'embedding'), None)
        
        # Revert document_id column type
        if document_id_col and document_id_col['type'].__class__.__name__ == 'VARCHAR':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN document_id TYPE INTEGER USING document_id::INTEGER
            """)
            print("✅ Reverted rag_chunks.document_id from VARCHAR(36) to INTEGER")
        
        # Revert embedding column type
        if embedding_col and embedding_col['type'].__class__.__name__ == 'JSON':
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN embedding TYPE BYTEA USING NULL
            """)
            print("✅ Reverted rag_chunks.embedding from JSON to LargeBinary")
    else:
        print("ℹ️ rag_chunks table doesn't exist") 