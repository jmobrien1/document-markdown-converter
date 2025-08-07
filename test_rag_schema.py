#!/usr/bin/env python3
"""
Simple script to test RAG schema directly
"""
import os
import sys

# Set environment variables to avoid problematic imports
os.environ['ENABLE_RAG'] = 'false'
os.environ['DISABLE_ML_IMPORTS'] = 'true'

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import tempfile

# Create a minimal Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Import models
from app.models import RAGChunk

with app.app_context():
    # Test creating the table
    print("Creating RAG chunks table...")
    db.create_all()
    
    # Check if table exists
    inspector = db.inspect(db.engine)
    if inspector.has_table('rag_chunks'):
        print("✅ RAG chunks table created successfully")
        
        # Get column info
        columns = inspector.get_columns('rag_chunks')
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
    else:
        print("❌ RAG chunks table not found")
    
    print("Schema test completed!") 