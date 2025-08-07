#!/usr/bin/env python3
"""
Direct RAG schema test without Alembic
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
from datetime import datetime

# Create a minimal Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Define the RAGChunk model directly
class RAGChunk(db.Model):
    """Model for storing document chunks for RAG."""
    __tablename__ = 'rag_chunks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey('conversions.id'), nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    chunk_text = db.Column(db.Text, nullable=False)
    embedding = db.Column(db.JSON, nullable=True)  # JSON for easier debugging and consistency
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    conversion = db.relationship('Conversion', backref=db.backref('rag_chunks', lazy=True))

    def __repr__(self):
        return f'<RAGChunk {self.id}: doc={self.document_id}, idx={self.chunk_index}>'

# Define a simple Conversion model for testing
class Conversion(db.Model):
    """Simple conversion model for testing foreign key"""
    __tablename__ = 'conversions'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    # Test creating the tables
    print("Creating tables...")
    db.create_all()
    
    # Check if table exists
    inspector = db.inspect(db.engine)
    if inspector.has_table('rag_chunks'):
        print("✅ RAG chunks table created successfully")
        
        # Get column info
        columns = inspector.get_columns('rag_chunks')
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
            
        # Test inserting a record
        try:
            # Create a test conversion first
            test_conversion = Conversion(filename='test.pdf')
            db.session.add(test_conversion)
            db.session.commit()
            
            # Create a test RAG chunk
            test_chunk = RAGChunk(
                document_id=test_conversion.id,
                chunk_index=0,
                chunk_text="This is a test chunk",
                embedding=[0.1, 0.2, 0.3]
            )
            db.session.add(test_chunk)
            db.session.commit()
            
            print("✅ Successfully inserted test RAG chunk")
            
            # Test querying
            chunks = RAGChunk.query.all()
            print(f"✅ Found {len(chunks)} RAG chunks in database")
            
        except Exception as e:
            print(f"❌ Error testing RAG chunks: {e}")
    else:
        print("❌ RAG chunks table not found")
    
    print("Schema test completed!") 