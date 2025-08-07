#!/usr/bin/env python3
"""
Simple script to check database status without loading ML dependencies
"""
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Create minimal Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Import only the models we need (without ML dependencies)
from app.models import User, Conversion, RAGChunk, RAGQuery

def check_database():
    """Check database status and tables"""
    print("🔍 Checking database status...")
    
    try:
        with app.app_context():
            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"✅ Database connected. Tables: {tables}")
            
            # Check if RAG tables exist
            if 'rag_chunks' in tables:
                print("✅ rag_chunks table exists")
            else:
                print("❌ rag_chunks table missing")
                
            if 'rag_queries' in tables:
                print("✅ rag_queries table exists")
            else:
                print("❌ rag_queries table missing")
                
            # Check migration status
            from alembic import command
            from alembic.config import Config
            
            alembic_cfg = Config("migrations/alembic.ini")
            alembic_cfg.set_main_option("script_location", "migrations")
            
            try:
                current = command.current(alembic_cfg)
                print(f"✅ Current migration: {current}")
            except Exception as e:
                print(f"⚠️ Migration check failed: {e}")
                
    except Exception as e:
        print(f"❌ Database check failed: {e}")

if __name__ == "__main__":
    check_database() 