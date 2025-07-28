#!/usr/bin/env python3
"""
Comprehensive script to fix the Render PostgreSQL database.
This script adds ALL missing columns to the users table.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def fix_render_database():
    """Fix the Render PostgreSQL database by adding all missing columns."""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Fixing Render PostgreSQL database...")
            print("=" * 60)
            
            # Get database type
            engine = db.engine
            db_type = engine.dialect.name
            print(f"📋 Database type: {db_type}")
            
            # Define ALL columns that might be missing
            columns_to_add = [
                ('subscription_status', 'VARCHAR(50)', 'DEFAULT \'trial\''),
                ('current_tier', 'VARCHAR(50)', 'DEFAULT \'free\''),
                ('subscription_start_date', 'TIMESTAMP', ''),
                ('last_payment_date', 'TIMESTAMP', ''),
                ('next_payment_date', 'TIMESTAMP', ''),
                ('trial_start_date', 'TIMESTAMP', ''),
                ('trial_end_date', 'TIMESTAMP', ''),
                ('on_trial', 'BOOLEAN', 'DEFAULT FALSE'),
                ('pro_pages_processed_current_month', 'INTEGER', 'DEFAULT 0')
            ]
            
            # Add columns one by one
            for column_name, data_type, default_value in columns_to_add:
                try:
                    print(f"➕ Adding column: {column_name}")
                    
                    # Use IF NOT EXISTS for PostgreSQL
                    if default_value:
                        sql = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {data_type} {default_value}"
                    else:
                        sql = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {data_type}"
                    
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
                        current_tier = 'free',
                        on_trial = FALSE,
                        pro_pages_processed_current_month = 0
                    WHERE subscription_status IS NULL 
                       OR current_tier IS NULL 
                       OR on_trial IS NULL 
                       OR pro_pages_processed_current_month IS NULL
                """))
                print("✅ Updated existing users with default values")
            except Exception as e:
                print(f"⚠️ Warning updating users: {e}")
            
            # Commit the changes
            db.session.commit()
            print("✅ Render database schema updated successfully!")
            
            # Test that the columns work
            print("🧪 Testing column access...")
            try:
                # Try to query a user with the new columns
                result = db.session.execute(text("""
                    SELECT id, email, subscription_status, current_tier, on_trial, pro_pages_processed_current_month 
                    FROM users LIMIT 1
                """))
                user_data = result.fetchone()
                if user_data:
                    print(f"✅ Successfully queried user with new columns:")
                    print(f"   - ID: {user_data[0]}")
                    print(f"   - Email: {user_data[1]}")
                    print(f"   - Subscription Status: {user_data[2]}")
                    print(f"   - Current Tier: {user_data[3]}")
                    print(f"   - On Trial: {user_data[4]}")
                    print(f"   - Pro Pages This Month: {user_data[5]}")
                else:
                    print("⚠️ No users found to test with")
            except Exception as e:
                print(f"❌ Error testing columns: {e}")
            
            # Test the User model methods
            print("🧪 Testing User model methods...")
            try:
                from app.models import User
                user = User.query.first()
                if user:
                    print(f"✅ User model test:")
                    print(f"   - Has Pro Access: {user.has_pro_access}")
                    print(f"   - Trial Days Remaining: {user.trial_days_remaining}")
                    print(f"   - Can Access Pro Features: {user.can_access_pro_features()}")
                else:
                    print("⚠️ No users found for model testing")
            except Exception as e:
                print(f"❌ Error testing User model: {e}")
            
            print("=" * 60)
            print("🎉 Render database fix completed!")
            print("All missing subscription columns have been added.")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Render database fix failed: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function to run the Render database fix."""
    success = fix_render_database()
    
    if success:
        print("\n✅ Render database schema is now up to date!")
        print("The column errors should be completely resolved.")
        print("\n📋 What's fixed:")
        print("   ✅ subscription_status column")
        print("   ✅ current_tier column")
        print("   ✅ subscription_start_date column")
        print("   ✅ last_payment_date column")
        print("   ✅ next_payment_date column")
        print("   ✅ trial_start_date column")
        print("   ✅ trial_end_date column")
        print("   ✅ on_trial column")
        print("   ✅ pro_pages_processed_current_month column")
        print("\n🚀 Next steps:")
        print("1. Deploy to Render")
        print("2. The /account page should work")
        print("3. Pro features should be accessible")
        print("4. All user relationships should work")
    else:
        print("\n❌ Render database fix failed.")
        print("Please check the error messages above.")

if __name__ == "__main__":
    main() 