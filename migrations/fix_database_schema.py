#!/usr/bin/env python3
"""
Database Schema Fix Script
Fixes missing trial columns in the users table.
This script works within the Flask app context to ensure proper configuration.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError, OperationalError

def get_database_url():
    """Get database URL from environment or config."""
    # Try environment variable first
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        # Handle SQLAlchemy 1.4+ compatibility
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    
    # Fallback to local SQLite for development
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return f'sqlite:///{os.path.join(basedir, "app.db")}'

def check_and_fix_schema():
    """Check and fix the database schema."""
    
    database_url = get_database_url()
    print(f"🔗 Using database: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    
    # Create engine
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if users table exists - handle both PostgreSQL and SQLite
            if 'postgresql' in database_url or 'postgres' in database_url:
                # PostgreSQL syntax
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'users'
                    )
                """))
            else:
                # SQLite syntax
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM sqlite_master 
                        WHERE type='table' AND name='users'
                    )
                """))
            
            if not result.scalar():
                print("❌ Users table does not exist!")
                return False
            
            print("✅ Users table exists")
            
            # Check existing columns - handle both PostgreSQL and SQLite
            if 'postgresql' in database_url or 'postgres' in database_url:
                # PostgreSQL syntax
                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    ORDER BY ordinal_position
                """))
            else:
                # SQLite syntax
                result = conn.execute(text("PRAGMA table_info(users)"))
            
            if 'postgresql' in database_url or 'postgres' in database_url:
                existing_columns = {row[0]: row[1] for row in result}
            else:
                existing_columns = {row[1]: row[2] for row in result}  # SQLite: name, type
            
            print(f"📋 Existing columns: {list(existing_columns.keys())}")
            
            # Define required columns
            required_columns = {
                'trial_start_date': 'TIMESTAMP',
                'trial_end_date': 'TIMESTAMP', 
                'on_trial': 'BOOLEAN',
                'pro_pages_processed_current_month': 'INTEGER'
            }
            
            # Add missing columns
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    print(f"➕ Adding {column_name} column...")
                    
                    if column_type == 'BOOLEAN':
                        sql = f"ALTER TABLE users ADD COLUMN {column_name} BOOLEAN DEFAULT TRUE"
                    elif column_type == 'INTEGER':
                        sql = f"ALTER TABLE users ADD COLUMN {column_name} INTEGER DEFAULT 0"
                    else:
                        sql = f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                    
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        print(f"✅ Added {column_name} column")
                    except Exception as e:
                        print(f"❌ Failed to add {column_name}: {e}")
                        return False
                else:
                    print(f"✅ {column_name} column already exists")
            
            # Check conversions table for pages_processed column
            if 'postgresql' in database_url or 'postgres' in database_url:
                # PostgreSQL syntax
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'conversions'
                    )
                """))
            else:
                # SQLite syntax
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM sqlite_master 
                        WHERE type='table' AND name='conversions'
                    )
                """))
            
            if result.scalar():
                if 'postgresql' in database_url or 'postgres' in database_url:
                    # PostgreSQL syntax
                    result = conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'conversions' AND column_name = 'pages_processed'
                    """))
                else:
                    # SQLite syntax
                    result = conn.execute(text("PRAGMA table_info(conversions)"))
                    result = [row for row in result if row[1] == 'pages_processed']
                
                if not result.fetchone():
                    print("➕ Adding pages_processed column to conversions table...")
                    try:
                        conn.execute(text("ALTER TABLE conversions ADD COLUMN pages_processed INTEGER"))
                        conn.commit()
                        print("✅ Added pages_processed column to conversions table")
                    except Exception as e:
                        print(f"❌ Failed to add pages_processed: {e}")
                        return False
                else:
                    print("✅ pages_processed column already exists in conversions table")
            
            print("🎉 Database schema fix completed successfully!")
            return True
            
    except ProgrammingError as e:
        print(f"❌ Database programming error: {e}")
        return False
    except OperationalError as e:
        print(f"❌ Database operational error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main function."""
    print("🚀 Starting database schema fix...")
    print("=" * 50)
    
    success = check_and_fix_schema()
    
    print("=" * 50)
    if success:
        print("✅ Database schema fix completed successfully!")
        print("🔄 You can now restart your application.")
        sys.exit(0)
    else:
        print("❌ Database schema fix failed!")
        print("💡 Please check the error messages above and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main() 