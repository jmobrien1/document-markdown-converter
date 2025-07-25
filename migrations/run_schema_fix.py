#!/usr/bin/env python3
"""
Flask App Context Database Schema Fix
Run this script within the Flask app context to fix missing trial columns.
"""

import os
import sys
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError

def fix_database_schema():
    """Fix the database schema within Flask app context."""
    from app import create_app, db
    
    app = create_app()
    
    with app.app_context():
        print("🚀 Starting database schema fix within Flask app context...")
        print("=" * 60)
        
        try:
            # Check if users table exists
            result = db.session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'users'
                )
            """))
            
            if not result.scalar():
                print("❌ Users table does not exist!")
                return False
            
            print("✅ Users table exists")
            
            # Check existing columns
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position
            """))
            
            existing_columns = {row[0]: row[1] for row in result}
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
                        db.session.execute(text(sql))
                        db.session.commit()
                        print(f"✅ Added {column_name} column")
                    except Exception as e:
                        db.session.rollback()
                        print(f"❌ Failed to add {column_name}: {e}")
                        return False
                else:
                    print(f"✅ {column_name} column already exists")
            
            # Check conversions table for pages_processed column
            result = db.session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'conversions'
                )
            """))
            
            if result.scalar():
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'conversions' AND column_name = 'pages_processed'
                """))
                
                if not result.fetchone():
                    print("➕ Adding pages_processed column to conversions table...")
                    try:
                        db.session.execute(text("ALTER TABLE conversions ADD COLUMN pages_processed INTEGER"))
                        db.session.commit()
                        print("✅ Added pages_processed column to conversions table")
                    except Exception as e:
                        db.session.rollback()
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
    success = fix_database_schema()
    
    print("=" * 60)
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