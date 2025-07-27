#!/usr/bin/env python3
"""
Script to add missing subscription columns to the users table.
This handles both PostgreSQL and SQLite databases.
"""

import os
import sys
from sqlalchemy import text, create_engine
from app import create_app, db

def add_subscription_columns():
    """Add missing subscription columns to users table."""
    app = create_app('production')
    
    with app.app_context():
        try:
            # Check database type
            engine = db.engine
            db_url = str(engine.url)
            
            if 'postgresql' in db_url or 'postgres' in db_url:
                print("Detected PostgreSQL database")
                add_columns_postgresql()
            else:
                print("Detected SQLite database")
                add_columns_sqlite()
                
        except Exception as e:
            print(f"Error adding columns: {e}")
            return False
    
    return True

def add_columns_postgresql():
    """Add columns to PostgreSQL database."""
    columns_to_add = [
        ('subscription_status', 'VARCHAR(50) DEFAULT \'trial\''),
        ('current_tier', 'VARCHAR(50) DEFAULT \'free\''),
        ('subscription_start_date', 'TIMESTAMP'),
        ('last_payment_date', 'TIMESTAMP'),
        ('next_payment_date', 'TIMESTAMP'),
        ('trial_start_date', 'TIMESTAMP'),
        ('trial_end_date', 'TIMESTAMP'),
        ('on_trial', 'BOOLEAN DEFAULT TRUE'),
        ('pro_pages_processed_current_month', 'INTEGER DEFAULT 0')
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            # Check if column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = :column_name
            """), {'column_name': column_name})
            
            if not result.fetchone():
                # Add column
                db.session.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"))
                print(f"✅ Added column: {column_name}")
            else:
                print(f"⚠️  Column already exists: {column_name}")
                
        except Exception as e:
            print(f"❌ Error adding column {column_name}: {e}")

def add_columns_sqlite():
    """Add columns to SQLite database."""
    columns_to_add = [
        ('subscription_status', 'VARCHAR(50) DEFAULT \'trial\''),
        ('current_tier', 'VARCHAR(50) DEFAULT \'free\''),
        ('subscription_start_date', 'DATETIME'),
        ('last_payment_date', 'DATETIME'),
        ('next_payment_date', 'DATETIME'),
        ('trial_start_date', 'DATETIME'),
        ('trial_end_date', 'DATETIME'),
        ('on_trial', 'BOOLEAN DEFAULT 1'),
        ('pro_pages_processed_current_month', 'INTEGER DEFAULT 0')
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            # Check if column exists
            result = db.session.execute(text("PRAGMA table_info(users)"))
            existing_columns = [row[1] for row in result.fetchall()]
            
            if column_name not in existing_columns:
                # Add column
                db.session.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"))
                print(f"✅ Added column: {column_name}")
            else:
                print(f"⚠️  Column already exists: {column_name}")
                
        except Exception as e:
            print(f"❌ Error adding column {column_name}: {e}")
    
    db.session.commit()

if __name__ == "__main__":
    print("Adding missing subscription columns to users table...")
    success = add_subscription_columns()
    if success:
        print("✅ Column addition completed successfully!")
    else:
        print("❌ Column addition failed!")
        sys.exit(1) 