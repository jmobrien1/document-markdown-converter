#!/usr/bin/env python3
"""
Comprehensive script to set up pro account and test session fixes.
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
            print("Creating user account...")
            
            # Create the user account
            user = User(email=email)
            user.password = "testpassword123"  # Simple password for testing
            
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
                db.session.add(user)
                db.session.commit()
                print(f"✅ Created new user account: {email}")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error creating user: {e}")
                return False
        else:
            print(f"✅ Found existing user: {user.email}")
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
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error upgrading user: {e}")
                return False
        
        print(f"   New status: {user.subscription_status}")
        print(f"   New tier: {user.current_tier}")
        print(f"   Trial end: {user.trial_end_date}")
        print(f"   Pro access: {user.has_pro_access}")
        return True

def test_session_fix():
    """Test that the session fix works properly."""
    app = create_app()
    
    with app.app_context():
        # Find the user to test with
        user = User.query.filter_by(email="obrienmike+123@gmail.com").first()
        if not user:
            print("❌ Test user not found. Please run setup first.")
            return False
        
        print(f"✅ Found test user: {user.email}")
        
        # Test the get_user_safely method
        try:
            fresh_user = User.get_user_safely(user.id)
            if not fresh_user:
                print("❌ get_user_safely returned None")
                return False
            
            print("✅ get_user_safely worked")
            
            # Test accessing conversions (this was causing the DetachedInstanceError)
            try:
                conversions_count = fresh_user.conversions.count()
                print(f"✅ Successfully accessed conversions: {conversions_count} conversions")
                
                # Test accessing other relationships
                daily_conversions = fresh_user.get_daily_conversions()
                print(f"✅ Successfully accessed daily conversions: {daily_conversions}")
                
                # Test accessing properties
                has_pro_access = fresh_user.has_pro_access
                print(f"✅ Successfully accessed has_pro_access: {has_pro_access}")
                
                # Test accessing trial information
                trial_days = fresh_user.trial_days_remaining
                print(f"✅ Successfully accessed trial_days_remaining: {trial_days}")
                
                return True
                
            except Exception as e:
                print(f"❌ Error accessing user relationships: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error in get_user_safely: {e}")
            return False

def main():
    """Main function to run the complete setup and test."""
    email = "obrienmike+123@gmail.com"
    
    print("🔧 Setting up PRO user and testing session fixes")
    print("=" * 60)
    
    # Step 1: Set up pro user
    print("📋 Step 1: Setting up PRO user account...")
    setup_success = setup_pro_user(email)
    
    if not setup_success:
        print("❌ Failed to set up PRO user. Exiting.")
        return
    
    print("\n" + "=" * 60)
    
    # Step 2: Test session fix
    print("🧪 Step 2: Testing session fix...")
    test_success = test_session_fix()
    
    if not test_success:
        print("❌ Session fix test failed.")
        return
    
    print("\n" + "=" * 60)
    print("🎉 All tests passed!")
    print("\n✅ PRO user setup complete!")
    print("✅ Session fix verified!")
    print("\nYou can now:")
    print("  🔗 Sign in to the app with: obrienmike+123@gmail.com")
    print("  🔑 Password: testpassword123")
    print("  🚀 Test Pro features:")
    print("    - Pro document conversion")
    print("    - Batch processing")
    print("    - Multi-format exports")
    print("    - Account page should work without errors")

if __name__ == "__main__":
    main() 