#!/usr/bin/env python3
"""
Create missing RAG database tables for vector storage.
This script creates the tables needed for RAG functionality.
"""

from app import create_app, db
from sqlalchemy import text

app = create_app()

def create_rag_tables():
    """Create RAG tables if they don't exist"""
    with app.app_context():
        try:
            print("🔧 Creating RAG database tables...")
            
            # Create rag_chunks table
            create_rag_chunks = text("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id VARCHAR(36) PRIMARY KEY,
                    document_id VARCHAR(36) NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create rag_documents table
            create_rag_documents = text("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id VARCHAR(36) PRIMARY KEY,
                    document_id VARCHAR(36) NOT NULL UNIQUE,
                    title VARCHAR(255),
                    content TEXT,
                    embedding JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create rag_queries table
            create_rag_queries = text("""
                CREATE TABLE IF NOT EXISTS rag_queries (
                    id VARCHAR(36) PRIMARY KEY,
                    document_id VARCHAR(36) NOT NULL,
                    query_text TEXT NOT NULL,
                    answer_text TEXT,
                    relevant_chunks JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create indexes for performance
            create_chunks_index = text("""
                CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id 
                ON rag_chunks(document_id);
            """)
            
            create_documents_index = text("""
                CREATE INDEX IF NOT EXISTS idx_rag_documents_document_id 
                ON rag_documents(document_id);
            """)
            
            create_queries_index = text("""
                CREATE INDEX IF NOT EXISTS idx_rag_queries_document_id 
                ON rag_queries(document_id);
            """)
            
            # Execute the SQL
            print("📝 Creating rag_chunks table...")
            db.session.execute(create_rag_chunks)
            
            print("📝 Creating rag_documents table...")
            db.session.execute(create_rag_documents)
            
            print("📝 Creating rag_queries table...")
            db.session.execute(create_rag_queries)
            
            print("🔍 Creating indexes...")
            db.session.execute(create_chunks_index)
            db.session.execute(create_documents_index)
            db.session.execute(create_queries_index)
            
            db.session.commit()
            print("✅ RAG tables created successfully!")
            
            # Verify tables exist (works with both SQLite and PostgreSQL)
            print("🔍 Verifying tables exist...")
            tables_to_check = ['rag_chunks', 'rag_documents', 'rag_queries']
            
            # Detect database type
            db_url = str(db.engine.url)
            is_postgres = 'postgresql' in db_url.lower()
            
            for table_name in tables_to_check:
                try:
                    if is_postgres:
                        # PostgreSQL verification
                        result = db.session.execute(
                            text("SELECT tablename FROM pg_tables WHERE tablename = :table_name;"),
                            {"table_name": table_name}
                        )
                    else:
                        # SQLite verification
                        result = db.session.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name;"),
                            {"table_name": table_name}
                        )
                    
                    if result.fetchone():
                        print(f"✅ {table_name} table confirmed in database")
                    else:
                        print(f"❌ {table_name} table not found")
                        
                except Exception as e:
                    print(f"⚠️ Could not verify {table_name} table: {e}")
                    
            print("🎉 RAG database setup complete!")
            
        except Exception as e:
            print(f"❌ Error creating RAG tables: {e}")
            db.session.rollback()
            raise

if __name__ == "__main__":
    create_rag_tables() 