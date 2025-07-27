#!/usr/bin/env python3
"""
Direct Expire Trials Script
This script can be run directly from the project root.
"""

import os
import sys
from datetime import datetime, timezone

def main():
    print(f"[{datetime.now(timezone.utc)}] Starting expire_trials task...")
    
    try:
        from app import create_app, db
        from app.models import User
        from sqlalchemy import text
        
        app = create_app('production')
        
        with app.app_context():
            # Check if trial columns exist
            database_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if 'postgresql' in database_url or 'postgres' in database_url:
                # PostgreSQL syntax
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name IN ('on_trial', 'trial_end_date')
                """))
                existing_columns = [row[0] for row in result]
            else:
                # SQLite syntax
                result = db.session.execute(text("PRAGMA table_info(users)"))
                existing_columns = [row[1] for row in result if row[1] in ('on_trial', 'trial_end_date')]
            
            if 'on_trial' not in existing_columns or 'trial_end_date' not in existing_columns:
                print("Trial columns don't exist yet, skipping trial expiration")
                return True
            
            # Find users whose trial has expired
            expired_users = User.query.filter(
                User.on_trial == True,
                User.trial_end_date < datetime.now(timezone.utc)
            ).all()
            
            expired_count = 0
            for user in expired_users:
                user.on_trial = False
                expired_count += 1
            
            if expired_count > 0:
                db.session.commit()
                print(f"Expired {expired_count} user trials")
            else:
                print("No trials to expire")
            
            print("✅ Expire trials task completed successfully")
            return True
                
    except Exception as e:
        print(f"❌ Error expiring trials: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 