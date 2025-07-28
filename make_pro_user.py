#!/usr/bin/env python3
"""
Quick script to make obrienmike+123@gmail.com a pro user for testing.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def make_pro_user():
    """Make obrienmike+123@gmail.com a pro user."""
    email = "obrienmike+123@gmail.com"
    
    app = create_app()
    
    with app.app_context():
        # Find the user by email
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"❌ User with email {email} not found.")
            print("Please create an account first by signing up at the application.")
            print("Then run this script again.")
            return False
        
        print(f"✅ Found user: {user.email}")
        
        # Set up pro access
        user.is_premium = True
        user.subscription_status = 'active'
        user.current_tier = 'pro'
        user.subscription_start_date = datetime.now(timezone.utc)
        user.last_payment_date = datetime.now(timezone.utc)
        user.next_payment_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Set trial to active (for testing purposes)
        user.on_trial = True
        user.trial_start_date = datetime.now(timezone.utc)
        user.trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Reset usage tracking
        user.pro_pages_processed_current_month = 0
        
        try:
            db.session.commit()
            print("✅ Successfully upgraded user to PRO status!")
            print(f"   New status: {user.subscription_status}")
            print(f"   New tier: {user.current_tier}")
            print(f"   Trial end: {user.trial_end_date}")
            print(f"   Pro access: {user.has_pro_access}")
            print("\n🎉 You can now test Pro features in the app!")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error upgrading user: {e}")
            return False

if __name__ == "__main__":
    print("🔧 Setting up PRO user for obrienmike+123@gmail.com")
    print("=" * 60)
    make_pro_user() 