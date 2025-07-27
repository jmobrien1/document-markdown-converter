#!/usr/bin/env python3
"""
Direct Reset Monthly Usage Script
This script can be run directly from the project root.
"""

import os
import sys
from datetime import datetime, timezone

def main():
    print(f"[{datetime.now(timezone.utc)}] Starting reset_monthly_usage task...")
    
    try:
        from app import create_app, db
        from app.models import User
        from sqlalchemy import text
        
        app = create_app('production')
        
        with app.app_context():
            # Check if the column exists
            database_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if 'postgresql' in database_url or 'postgres' in database_url:
                # PostgreSQL syntax
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'pro_pages_processed_current_month'
                """))
                column_exists = result.fetchone() is not None
            else:
                # SQLite syntax
                result = db.session.execute(text("PRAGMA table_info(users)"))
                column_exists = any(row[1] == 'pro_pages_processed_current_month' for row in result)
            
            if not column_exists:
                print("pro_pages_processed_current_month column doesn't exist yet, skipping reset")
                return True
            
            # Reset monthly usage for all users
            updated_count = db.session.execute(
                text("UPDATE users SET pro_pages_processed_current_month = 0")
            ).rowcount
            
            db.session.commit()
            
            print(f"Reset monthly usage for {updated_count} users")
            print("✅ Reset monthly usage task completed successfully")
            return True
                
    except Exception as e:
        print(f"❌ Error resetting monthly usage: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 