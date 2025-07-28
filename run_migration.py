#!/usr/bin/env python3
"""
Script to run the migration and add missing subscription columns.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def run_migration():
    """Run the migration to add missing subscription columns."""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Running migration to add missing subscription columns...")
            print("=" * 60)
            
            # Check current table structure
            print("📋 Checking current table structure...")
            result = db.session.execute(
                text("""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name IN ('subscription_status', 'current_tier', 'subscription_start_date', 'last_payment_date', 'next_payment_date')
                    ORDER BY column_name
                """)
            ).fetchall()
            
            existing_columns = [row[0] for row in result]
            print(f"✅ Found existing columns: {existing_columns}")
            
            # Add missing columns
            columns_to_add = [
                ('subscription_status', 'VARCHAR(50)', 'DEFAULT \'trial\''),
                ('current_tier', 'VARCHAR(50)', 'DEFAULT \'free\''),
                ('subscription_start_date', 'TIMESTAMP', ''),
                ('last_payment_date', 'TIMESTAMP', ''),
                ('next_payment_date', 'TIMESTAMP', '')
            ]
            
            for column_name, data_type, default_value in columns_to_add:
                if column_name not in existing_columns:
                    print(f"➕ Adding column: {column_name}")
                    sql = f"ALTER TABLE users ADD COLUMN {column_name} {data_type} {default_value}"
                    db.session.execute(text(sql))
                else:
                    print(f"✅ Column already exists: {column_name}")
            
            # Update existing users with default values
            print("🔄 Updating existing users with default values...")
            db.session.execute(text("""
                UPDATE users SET 
                    subscription_status = 'trial',
                    current_tier = 'free'
                WHERE subscription_status IS NULL OR current_tier IS NULL
            """))
            
            # Commit the changes
            db.session.commit()
            print("✅ Migration completed successfully!")
            
            # Verify the changes
            print("🔍 Verifying changes...")
            result = db.session.execute(
                text("""
                    SELECT column_name, data_type, is_nullable, column_default 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name IN ('subscription_status', 'current_tier', 'subscription_start_date', 'last_payment_date', 'next_payment_date')
                    ORDER BY column_name
                """)
            ).fetchall()
            
            print("📋 Final table structure:")
            for row in result:
                print(f"   - {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
            
            print("=" * 60)
            print("🎉 Migration completed successfully!")
            print("The missing subscription columns have been added to your database.")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function to run the migration."""
    success = run_migration()
    
    if success:
        print("\n✅ Database schema is now up to date!")
        print("You can now deploy your application without the column errors.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")

if __name__ == "__main__":
    main() 