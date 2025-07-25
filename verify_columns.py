#!/usr/bin/env python3
"""
Verify Database Columns
Checks if all required columns exist in the database.
"""

import os
import sys
from sqlalchemy import create_engine, text

def main():
    print("🔍 Database Column Verification")
    print("=" * 40)
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set!")
        return False
    
    print(f"🔗 Connecting to database...")
    
    # Create engine
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            print("✅ Connected to database")
            
            # Check users table columns
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'users'
                ORDER BY ordinal_position
            """))
            
            user_columns = {row[0]: row[1] for row in result}
            print(f"\n📋 Users table columns ({len(user_columns)} total):")
            for col, dtype in user_columns.items():
                print(f"  - {col}: {dtype}")
            
            # Check for required columns
            required_user_columns = [
                'trial_start_date', 'trial_end_date', 'on_trial', 'pro_pages_processed_current_month'
            ]
            
            print(f"\n🔍 Checking required user columns:")
            missing_columns = []
            for col in required_user_columns:
                if col in user_columns:
                    print(f"  ✅ {col}: {user_columns[col]}")
                else:
                    print(f"  ❌ {col}: MISSING")
                    missing_columns.append(col)
            
            # Check conversions table
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns 
                WHERE table_name = 'conversions'
                ORDER BY ordinal_position
            """))
            
            conversion_columns = {row[0]: row[1] for row in result}
            print(f"\n📋 Conversions table columns ({len(conversion_columns)} total):")
            for col, dtype in conversion_columns.items():
                print(f"  - {col}: {dtype}")
            
            # Check for pages_processed
            if 'pages_processed' in conversion_columns:
                print(f"  ✅ pages_processed: {conversion_columns['pages_processed']}")
            else:
                print(f"  ❌ pages_processed: MISSING")
                missing_columns.append('conversions.pages_processed')
            
            # Summary
            if missing_columns:
                print(f"\n❌ Missing columns: {missing_columns}")
                print("💡 Run add_missing_columns.py to fix this.")
                return False
            else:
                print(f"\n🎉 All required columns are present!")
                print("✅ Your database schema is correct.")
                return True
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 