#!/usr/bin/env python3
"""
Verification script for Reverse Trial Implementation
Tests that new users get 14-day Pro trial upon signup
"""

import sqlite3
from datetime import datetime, timedelta, timezone
import os

def verify_trial_implementation():
    """Verify that the reverse trial implementation is working correctly."""
    
    # Connect to the database
    db_path = 'app.db'
    if not os.path.exists(db_path):
        print("❌ Database file not found. Please run the application first.")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 VERIFYING REVERSE TRIAL IMPLEMENTATION")
        print("=" * 50)
        
        # 1. Find the most recently created user
        cursor.execute("""
            SELECT id, email, created_at, on_trial, trial_start_date, trial_end_date
            FROM users 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        
        user = cursor.fetchone()
        if not user:
            print("❌ No users found in database")
            return False
        
        user_id, email, created_at, on_trial, trial_start_date, trial_end_date = user
        
        print(f"📧 Most recent user: {email}")
        print(f"🆔 User ID: {user_id}")
        print(f"📅 Created at: {created_at}")
        print(f"🎁 On trial: {on_trial}")
        print(f"📅 Trial start: {trial_start_date}")
        print(f"📅 Trial end: {trial_end_date}")
        
        # 2. Verify trial status
        if not on_trial:
            print("❌ User is not on trial")
            return False
        
        if not trial_start_date or not trial_end_date:
            print("❌ Trial dates not set")
            return False
        
        print("✅ Trial status verified")
        
        # 3. Verify trial duration (should be 14 days)
        try:
            start_date = datetime.fromisoformat(trial_start_date.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(trial_end_date.replace('Z', '+00:00'))
            
            trial_duration = (end_date - start_date).days
            print(f"📊 Trial duration: {trial_duration} days")
            
            if trial_duration != 14:
                print(f"❌ Trial duration is {trial_duration} days, expected 14 days")
                return False
            
            print("✅ Trial duration verified (14 days)")
            
        except Exception as e:
            print(f"❌ Error parsing trial dates: {e}")
            return False
        
        # 4. Verify trial end date is in the future
        now = datetime.now(timezone.utc)
        if end_date <= now:
            print("❌ Trial has already ended")
            return False
        
        days_remaining = (end_date - now).days
        print(f"⏰ Days remaining: {days_remaining}")
        print("✅ Trial is active")
        
        # 5. Check if user has pro access
        cursor.execute("""
            SELECT has_pro_access FROM users WHERE id = ?
        """, (user_id,))
        
        has_pro_access = cursor.fetchone()[0]
        print(f"💎 Has pro access: {has_pro_access}")
        
        if not has_pro_access:
            print("❌ User doesn't have pro access despite being on trial")
            return False
        
        print("✅ Pro access verified")
        
        conn.close()
        
        print("\n🎉 ALL VERIFICATIONS PASSED!")
        print("✅ Reverse trial implementation is working correctly")
        print(f"✅ User {email} has 14-day Pro trial with {days_remaining} days remaining")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False

if __name__ == "__main__":
    success = verify_trial_implementation()
    exit(0 if success else 1) 