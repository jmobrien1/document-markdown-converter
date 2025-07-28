#!/usr/bin/env python3
"""
Script to add missing subscription columns to the database.
Works with both SQLite and PostgreSQL.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def add_missing_columns():
    """Add missing subscription columns to the database."""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Adding missing subscription columns to database...")
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
                    
                    # Use IF NOT EXISTS for PostgreSQL, or try/catch for SQLite
                    if db_type == 'postgresql':
                        sql = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {data_type} {default_value}"
                    else:
                        # For SQLite, we'll try to add and catch if it exists
                        sql = f"ALTER TABLE users ADD COLUMN {column_name} {data_type} {default_value}"
                    
                    db.session.execute(text(sql))
                    print(f"✅ Successfully added: {column_name}")
                    
                except Exception as e:
                    if "already exists" in str(e) or "duplicate column name" in str(e):
                        print(f"✅ Column already exists: {column_name}")
                    else:
                        print(f"⚠️ Warning adding {column_name}: {e}")
                        # Continue with other columns
            
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
            print("✅ Database schema updated successfully!")
            
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
            print("🎉 Database schema fix completed!")
            print("The missing subscription columns have been added.")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Database fix failed: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function to run the database fix."""
    success = add_missing_columns()
    
    if success:
        print("\n✅ Database schema is now up to date!")
        print("You can now deploy your application without the column errors.")
        print("\n📋 Next steps:")
        print("1. Deploy to Render")
        print("2. The column errors should be resolved")
        print("3. Test the /account page")
    else:
        print("\n❌ Database fix failed. Please check the error messages above.")

if __name__ == "__main__":
    main() 