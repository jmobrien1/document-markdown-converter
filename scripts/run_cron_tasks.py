#!/usr/bin/env python3
"""
Direct Cron Task Runner
This script runs cron tasks directly without Celery, making it more reliable for cron jobs.
"""

import os
import sys
from datetime import datetime, timezone

def run_expire_trials():
    """Run the expire trials task directly."""
    try:
        from app import create_app, db
        from app.models import User
        from sqlalchemy import text
        
        app = create_app('production')
        
        with app.app_context():
            print(f"[{datetime.now(timezone.utc)}] Starting expire_trials task...")
            
            # Check if trial columns exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('on_trial', 'trial_end_date')
            """))
            existing_columns = [row[0] for row in result]
            
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
            
            return True
                
    except Exception as e:
        print(f"Error expiring trials: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False

def run_reset_monthly_usage():
    """Run the reset monthly usage task directly."""
    try:
        from app import create_app, db
        from app.models import User
        from sqlalchemy import text
        
        app = create_app('production')
        
        with app.app_context():
            print(f"[{datetime.now(timezone.utc)}] Starting reset_monthly_usage task...")
            
            # Check if the column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'pro_pages_processed_current_month'
            """))
            
            if not result.fetchone():
                print("pro_pages_processed_current_month column doesn't exist yet, skipping reset")
                return True
            
            # Reset all users' monthly page count
            updated_count = User.query.update({
                User.pro_pages_processed_current_month: 0
            })
            
            db.session.commit()
            print(f"Reset monthly usage for {updated_count} users")
            
            return True
                
    except Exception as e:
        print(f"Error resetting monthly usage: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False

def run_redis_health_check():
    """Run the Redis health check task directly."""
    try:
        from app import create_app
        from app.tasks import redis_health_check
        
        app = create_app('production')
        
        with app.app_context():
            print(f"[{datetime.now(timezone.utc)}] Starting redis_health_check task...")
            
            # Run the task directly
            result = redis_health_check()
            print(f"Redis health check result: {result}")
            
            return True
                
    except Exception as e:
        print(f"Error running Redis health check: {str(e)}")
        return False

def main():
    """Main function to run the specified task."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_cron_tasks.py <task_name>")
        print("Available tasks: expire_trials, reset_monthly_usage, redis_health_check")
        sys.exit(1)
    
    task_name = sys.argv[1]
    
    print(f"Running task: {task_name}")
    print("=" * 50)
    
    if task_name == "expire_trials":
        success = run_expire_trials()
    elif task_name == "reset_monthly_usage":
        success = run_reset_monthly_usage()
    elif task_name == "redis_health_check":
        success = run_redis_health_check()
    else:
        print(f"Unknown task: {task_name}")
        sys.exit(1)
    
    print("=" * 50)
    if success:
        print(f"Task {task_name} completed successfully!")
        sys.exit(0)
    else:
        print(f"Task {task_name} failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 