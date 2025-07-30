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
            # Check if this is SQLite or PostgreSQL
            is_sqlite = 'sqlite' in database_url.lower()
            
            if is_sqlite:
                # SQLite doesn't have information_schema, so we'll try to add columns directly
                print("📋 SQLite database detected - adding columns directly...")
                
                # Add columns one by one, ignoring errors if they already exist
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN trial_start_date TIMESTAMP"))
                    print("✅ Added trial_start_date column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        print("ℹ️ trial_start_date column already exists")
                    else:
                        print(f"⚠️ Could not add trial_start_date: {e}")
                
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN trial_end_date TIMESTAMP"))
                    print("✅ Added trial_end_date column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        print("ℹ️ trial_end_date column already exists")
                    else:
                        print(f"⚠️ Could not add trial_end_date: {e}")
                
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN on_trial BOOLEAN DEFAULT 1"))
                    print("✅ Added on_trial column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        print("ℹ️ on_trial column already exists")
                    else:
                        print(f"⚠️ Could not add on_trial: {e}")
                
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN pro_pages_processed_current_month INTEGER DEFAULT 0"))
                    print("✅ Added pro_pages_processed_current_month column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        print("ℹ️ pro_pages_processed_current_month column already exists")
                    else:
                        print(f"⚠️ Could not add pro_pages_processed_current_month: {e}")
                
            else:
                # PostgreSQL - use information_schema
                print("📋 PostgreSQL database detected - checking existing columns...")
                
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