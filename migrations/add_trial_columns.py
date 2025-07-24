#!/usr/bin/env python3
"""
Migration script to add missing trial columns to users table.
Run this script to fix the database schema mismatch.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

def add_trial_columns():
    """Add missing trial columns to users table."""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        return False
    
    # Create engine
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('trial_start_date', 'trial_end_date', 'on_trial')
            """))
            existing_columns = [row[0] for row in result]
            
            print(f"📋 Existing trial columns: {existing_columns}")
            
            # Add missing columns
            if 'trial_start_date' not in existing_columns:
                print("➕ Adding trial_start_date column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN trial_start_date TIMESTAMP"))
                conn.commit()
                print("✅ Added trial_start_date column")
            
            if 'trial_end_date' not in existing_columns:
                print("➕ Adding trial_end_date column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN trial_end_date TIMESTAMP"))
                conn.commit()
                print("✅ Added trial_end_date column")
            
            if 'on_trial' not in existing_columns:
                print("➕ Adding on_trial column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN on_trial BOOLEAN DEFAULT TRUE"))
                conn.commit()
                print("✅ Added on_trial column")
            
            # Check if pro_pages_processed_current_month exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'pro_pages_processed_current_month'
            """))
            
            if not result.fetchone():
                print("➕ Adding pro_pages_processed_current_month column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN pro_pages_processed_current_month INTEGER DEFAULT 0"))
                conn.commit()
                print("✅ Added pro_pages_processed_current_month column")
            
            print("🎉 Migration completed successfully!")
            return True
            
    except ProgrammingError as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting database migration...")
    success = add_trial_columns()
    if success:
        print("✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("❌ Migration failed!")
        sys.exit(1) 