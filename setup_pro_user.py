#!/usr/bin/env python3
"""
Script to set up a pro user account for testing.
Run this script to upgrade a user to pro status.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def setup_pro_user(email):
    """Set up a user as a pro user for testing."""
    app = create_app()
    
    with app.app_context():
        # Find the user by email
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"❌ User with email {email} not found.")
            print("Please create an account first by signing up at the application.")
            return False
        
        print(f"✅ Found user: {user.email}")
        print(f"   Current status: {user.subscription_status}")
        print(f"   Current tier: {user.current_tier}")
        print(f"   Is premium: {user.is_premium}")
        
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
            return True
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error upgrading user: {e}")
            return False

def main():
    """Main function to run the script."""
    if len(sys.argv) != 2:
        print("Usage: python setup_pro_user.py <email>")
        print("Example: python setup_pro_user.py obrienmike+123@gmail.com")
        sys.exit(1)
    
    email = sys.argv[1]
    print(f"🔧 Setting up PRO user for: {email}")
    print("=" * 50)
    
    success = setup_pro_user(email)
    
    if success:
        print("=" * 50)
        print("🎉 PRO user setup complete!")
        print("You can now test the Pro features in the application.")
        print("Features available:")
        print("  ✅ Pro document conversion")
        print("  ✅ Batch processing")
        print("  ✅ Advanced OCR capabilities")
        print("  ✅ Multi-format exports")
    else:
        print("=" * 50)
        print("❌ PRO user setup failed.")
        print("Please ensure:")
        print("  1. The user account exists")
        print("  2. You're running this from the project root")
        print("  3. The database is accessible")

if __name__ == "__main__":
    main() 