#!/usr/bin/env python3
"""
Deployment script to fix the database schema on Render.
This script should be run on Render to add the missing columns.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def fix_production_database():
    """Fix the production database schema on Render."""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Fixing production database schema on Render...")
            print("=" * 60)
            
            # Get database type
            engine = db.engine
            db_type = engine.dialect.name
            print(f"📋 Database type: {db_type}")
            
            # Define columns to add
            columns_to_add = [
                ('subscription_status', 'VARCHAR(50)', 'DEFAULT \'trial\''),
                ('current_tier', 'VARCHAR(50)', 'DEFAULT \'free\''),
                ('subscription_start_date', 'TIMESTAMP', ''),
                ('last_payment_date', 'TIMESTAMP', ''),
                ('next_payment_date', 'TIMESTAMP', '')
            ]
            
            # Add columns one by one
            for column_name, data_type, default_value in columns_to_add:
                try:
                    print(f"➕ Adding column: {column_name}")
                    
                    # Use IF NOT EXISTS for PostgreSQL
                    sql = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {data_type} {default_value}"
                    db.session.execute(text(sql))
                    print(f"✅ Successfully added: {column_name}")
                    
                except Exception as e:
                    if "already exists" in str(e) or "duplicate column name" in str(e):
                        print(f"✅ Column already exists: {column_name}")
                    else:
                        print(f"❌ Error adding {column_name}: {e}")
                        return False
            
            # Update existing users with default values
            print("🔄 Updating existing users with default values...")
            try:
                db.session.execute(text("""
                    UPDATE users SET 
                        subscription_status = 'trial',
                        current_tier = 'free'
                    WHERE subscription_status IS NULL OR current_tier IS NULL
                """))
                print("✅ Updated existing users")
            except Exception as e:
                print(f"⚠️ Warning updating users: {e}")
            
            # Commit the changes
            db.session.commit()
            print("✅ Production database schema updated successfully!")
            
            # Test that the columns work
            print("🧪 Testing column access...")
            try:
                # Try to query a user with the new columns
                result = db.session.execute(text("SELECT id, email, subscription_status, current_tier FROM users LIMIT 1"))
                user_data = result.fetchone()
                if user_data:
                    print(f"✅ Successfully queried user with new columns:")
                    print(f"   - ID: {user_data[0]}")
                    print(f"   - Email: {user_data[1]}")
                    print(f"   - Subscription Status: {user_data[2]}")
                    print(f"   - Current Tier: {user_data[3]}")
                else:
                    print("⚠️ No users found to test with")
            except Exception as e:
                print(f"❌ Error testing columns: {e}")
            
            print("=" * 60)
            print("🎉 Production database fix completed!")
            print("The missing subscription columns have been added to Render.")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Production database fix failed: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function to run the production database fix."""
    success = fix_production_database()
    
    if success:
        print("\n✅ Production database schema is now up to date!")
        print("The column errors should be resolved on Render.")
        print("\n📋 Next steps:")
        print("1. The /account page should now work")
        print("2. Pro features should be accessible")
        print("3. All user relationships should work properly")
    else:
        print("\n❌ Production database fix failed.")
        print("Please check the error messages above.")

if __name__ == "__main__":
    main() 