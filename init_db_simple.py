#!/usr/bin/env python3
"""
Simple database initialization script that avoids problematic imports
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
from flask_migrate import Migrate
import tempfile

# Create a minimal Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Import models (without RAG service)
from app.models import User, Conversion, RAGChunk, RAGQuery, Team, TeamMember, Subscription, Invoice, Batch, ConversionJob, Summary, AnonymousUsage

def init_db():
    """Initialize the database"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables created successfully!")
        
        # Check if alembic_version table exists
        try:
            result = db.session.execute(db.text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            print(f"Current migration version: {current_version}")
        except Exception as e:
            print(f"No alembic_version table found: {e}")
            # Stamp with the latest migration
            try:
                from flask_migrate import stamp
                stamp()
                print("Database stamped with latest migration")
            except Exception as stamp_error:
                print(f"Error stamping database: {stamp_error}")

if __name__ == '__main__':
    init_db() 