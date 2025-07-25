#!/usr/bin/env python3
"""
Quick Database Schema Fix
Run this script to fix missing trial columns in the database.
"""

import os
import sys

def main():
    """Main function to run the schema fix."""
    print("🔧 Database Schema Fix Tool")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('app'):
        print("❌ Please run this script from the project root directory")
        sys.exit(1)
    
    # Try to run the Flask app context version first
    try:
        print("🔄 Attempting to run schema fix within Flask app context...")
        from migrations.run_schema_fix import fix_database_schema
        success = fix_database_schema()
        
        if success:
            print("✅ Schema fix completed successfully!")
            return True
        else:
            print("❌ Flask app context fix failed, trying direct database approach...")
            
    except ImportError as e:
        print(f"⚠️ Flask app context not available: {e}")
        print("🔄 Trying direct database approach...")
    except Exception as e:
        print(f"❌ Flask app context error: {e}")
        print("🔄 Trying direct database approach...")
    
    # Try the direct database approach
    try:
        from migrations.fix_database_schema import check_and_fix_schema
        success = check_and_fix_schema()
        
        if success:
            print("✅ Schema fix completed successfully!")
            return True
        else:
            print("❌ Direct database fix also failed")
            return False
            
    except Exception as e:
        print(f"❌ Direct database fix error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 Database schema has been fixed!")
        print("🔄 You can now restart your application.")
        sys.exit(0)
    else:
        print("\n❌ Database schema fix failed!")
        print("💡 Please check the error messages above.")
        print("🔧 You may need to manually run SQL commands:")
        print("   ALTER TABLE users ADD COLUMN trial_start_date TIMESTAMP;")
        print("   ALTER TABLE users ADD COLUMN trial_end_date TIMESTAMP;")
        print("   ALTER TABLE users ADD COLUMN on_trial BOOLEAN DEFAULT TRUE;")
        print("   ALTER TABLE users ADD COLUMN pro_pages_processed_current_month INTEGER DEFAULT 0;")
        sys.exit(1) 