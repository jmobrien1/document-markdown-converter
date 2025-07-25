#!/usr/bin/env python3
"""
Quick Database Column Fix
Adds missing trial and usage columns to the users table.
"""

import os
import sys
from sqlalchemy import create_engine, text

def main():
    print("🔧 Quick Database Column Fix")
    print("=" * 40)
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set!")
        print("💡 Make sure you're running this in your production environment.")
        return False
    
    print(f"🔗 Connecting to database...")
    
    # Create engine
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            print("✅ Connected to database")
            
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN (
                    'trial_start_date', 'trial_end_date', 'on_trial', 'pro_pages_processed_current_month'
                )
            """))
            
            existing_columns = [row[0] for row in result]
            print(f"📋 Existing trial columns: {existing_columns}")
            
            # Add missing columns
            columns_to_add = [
                ('trial_start_date', 'TIMESTAMP'),
                ('trial_end_date', 'TIMESTAMP'),
                ('on_trial', 'BOOLEAN DEFAULT TRUE'),
                ('pro_pages_processed_current_month', 'INTEGER DEFAULT 0')
            ]
            
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    print(f"➕ Adding {column_name} column...")
                    sql = f"ALTER TABLE users ADD COLUMN {column_name} {column_def}"
                    
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        print(f"✅ Added {column_name} column")
                    except Exception as e:
                        print(f"❌ Failed to add {column_name}: {e}")
                        return False
                else:
                    print(f"✅ {column_name} column already exists")
            
            # Check conversions table for pages_processed
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'conversions' AND column_name = 'pages_processed'
            """))
            
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
            
            print("\n🎉 All missing columns have been added successfully!")
            print("✅ Your app should now work without the column errors.")
            return True
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 