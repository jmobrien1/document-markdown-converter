"""Final RAG chunks schema fix - comprehensive migration

Revision ID: final_rag_fix_004
Revises: fix_rag_auto_increment_003
Create Date: 2025-08-05 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'final_rag_fix_004'
down_revision = 'fix_rag_auto_increment_003'
branch_labels = None
depends_on = None


def upgrade():
    """Comprehensive RAG schema fix with data migration"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if rag_chunks table exists
    if not inspector.has_table('rag_chunks'):
        # Create new table with proper schema
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
        return
    
    # Get current column info
    columns = inspector.get_columns('rag_chunks')
    column_info = {col['name']: col for col in columns}
    
    # Check if we need to migrate data
    needs_migration = False
    if 'id' in column_info and column_info['id']['type'].__class__.__name__ != 'INTEGER':
        needs_migration = True
    if 'document_id' in column_info and column_info['document_id']['type'].__class__.__name__ != 'INTEGER':
        needs_migration = True
    if 'embedding' in column_info and column_info['embedding']['type'].__class__.__name__ != 'JSON':
        needs_migration = True
    
    if needs_migration:
        # Backup existing data
        result = connection.execute(sa.text("SELECT COUNT(*) FROM rag_chunks"))
        row_count = result.scalar()
        
        if row_count > 0:
            # Create backup table
            op.execute("""
                CREATE TABLE rag_chunks_backup AS 
                SELECT * FROM rag_chunks
            """)
        
        # Drop and recreate table with proper schema
        op.drop_table('rag_chunks')
        
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
        
        # Migrate data if backup exists
        if row_count > 0:
            try:
                # Migrate data with type conversion
                op.execute("""
                    INSERT INTO rag_chunks (document_id, chunk_index, chunk_text, embedding, created_at)
                    SELECT 
                        CASE 
                            WHEN document_id ~ '^[0-9]+$' THEN document_id::integer
                            ELSE NULL
                        END as document_id,
                        chunk_index,
                        chunk_text,
                        CASE 
                            WHEN embedding IS NOT NULL THEN embedding::json
                            ELSE NULL
                        END as embedding,
                        created_at
                    FROM rag_chunks_backup
                    WHERE document_id ~ '^[0-9]+$'
                """)
                
                # Drop backup table
                op.drop_table('rag_chunks_backup')
                
            except Exception as e:
                # If migration fails, drop backup and continue
                op.execute("DROP TABLE IF EXISTS rag_chunks_backup")
                raise e
    else:
        # Just ensure proper constraints
        op.create_foreign_key(None, 'rag_chunks', 'conversions', ['document_id'], ['id'])


def downgrade():
    """Revert changes if needed"""
    # This is a schema fix - downgrade not implemented
    pass 