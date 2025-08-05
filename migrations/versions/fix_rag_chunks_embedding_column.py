"""Fix RAG chunks embedding column type

Revision ID: fix_rag_embedding_001
Revises: 
Create Date: 2025-08-05 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fix_rag_embedding_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Change embedding column from LargeBinary to JSON"""
    # Check if rag_chunks table exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if inspector.has_table('rag_chunks'):
        # Check current column type
        columns = inspector.get_columns('rag_chunks')
        embedding_col = next((col for col in columns if col['name'] == 'embedding'), None)
        
        if embedding_col and embedding_col['type'].__class__.__name__ == 'LargeBinary':
            # Change column type from LargeBinary to JSON
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN embedding TYPE JSON USING NULL
            """)
            print("✅ Changed rag_chunks.embedding from LargeBinary to JSON")
        else:
            print("ℹ️ rag_chunks.embedding column is already JSON or doesn't exist")
    else:
        print("ℹ️ rag_chunks table doesn't exist yet")


def downgrade():
    """Revert embedding column back to LargeBinary (if needed)"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if inspector.has_table('rag_chunks'):
        columns = inspector.get_columns('rag_chunks')
        embedding_col = next((col for col in columns if col['name'] == 'embedding'), None)
        
        if embedding_col and embedding_col['type'].__class__.__name__ == 'JSON':
            # Change column type from JSON to LargeBinary
            op.execute("""
                ALTER TABLE rag_chunks 
                ALTER COLUMN embedding TYPE BYTEA USING NULL
            """)
            print("✅ Reverted rag_chunks.embedding from JSON to LargeBinary")
        else:
            print("ℹ️ rag_chunks.embedding column is already LargeBinary or doesn't exist")
    else:
        print("ℹ️ rag_chunks table doesn't exist") 