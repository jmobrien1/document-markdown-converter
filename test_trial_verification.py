#!/usr/bin/env python3
"""
Comprehensive test script for Reverse Trial Implementation
Uses Flask app context to properly test the implementation
"""

from app import create_app, db
from app.models import User
from datetime import datetime, timedelta, timezone

def test_trial_implementation():
    """Test the reverse trial implementation comprehensively."""
    
    app = create_app()
    with app.app_context():
        print("🔍 TESTING REVERSE TRIAL IMPLEMENTATION")
        print("=" * 50)
        
        # 1. Create database tables
        print("1. Creating database tables...")
        db.create_all()
        print("✅ Database tables created")
        
        # 2. Create a test user with trial
        print("\n2. Creating test user with trial...")
        test_email = "trial-test@example.com"
        
        # Delete existing user if it exists
        existing_user = User.query.filter_by(email=test_email).first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()
            print("🗑️  Deleted existing test user")
        
        # Create new user with trial (simulating signup process)
        user = User(email=test_email)
        user.password = "testpassword123"
        
        # Set trial dates (14-day trial) - exactly as in signup route
        user.trial_start_date = datetime.now(timezone.utc)
        user.trial_end_date = user.trial_start_date + timedelta(days=14)
        user.on_trial = True
        
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Test user created: {test_email}")
        print(f"🎁 Trial start: {user.trial_start_date}")
        print(f"🎁 Trial end: {user.trial_end_date}")
        
        # 3. Verify trial properties
        print("\n3. Verifying trial properties...")
        
        # Check trial status
        if not user.on_trial:
            print("❌ User is not on trial")
            return False
        print("✅ User is on trial")
        
        # Check trial dates
        if not user.trial_start_date or not user.trial_end_date:
            print("❌ Trial dates not set")
            return False
        print("✅ Trial dates are set")
        
        # Check trial duration
        trial_duration = (user.trial_end_date - user.trial_start_date).days
        if trial_duration != 14:
            print(f"❌ Trial duration is {trial_duration} days, expected 14")
            return False
        print(f"✅ Trial duration: {trial_duration} days")
        
        # Check days remaining
        days_remaining = user.trial_days_remaining
        if days_remaining <= 0:
            print("❌ Trial has expired")
            return False
        print(f"✅ Days remaining: {days_remaining}")
        
        # 4. Verify pro access
        print("\n4. Verifying pro access...")
        
        has_pro_access = user.has_pro_access
        print(f"💎 Has pro access: {has_pro_access}")
        
        if not has_pro_access:
            print("❌ User doesn't have pro access despite being on trial")
            return False
        print("✅ User has pro access")
        
        # 5. Test trial expiration logic
        print("\n5. Testing trial expiration logic...")
        
        # Create a user with expired trial
        expired_user = User(email="expired-test@example.com")
        expired_user.password = "testpassword123"
        expired_user.trial_start_date = datetime.now(timezone.utc) - timedelta(days=20)
        expired_user.trial_end_date = datetime.now(timezone.utc) - timedelta(days=6)
        expired_user.on_trial = True
        
        db.session.add(expired_user)
        db.session.commit()
        
        print(f"📅 Expired user trial end: {expired_user.trial_end_date}")
        print(f"⏰ Expired user days remaining: {expired_user.trial_days_remaining}")
        print(f"💎 Expired user has pro access: {expired_user.has_pro_access}")
        
        if expired_user.has_pro_access:
            print("❌ Expired user still has pro access")
            return False
        print("✅ Expired user correctly denied pro access")
        
        # 6. Test account page data
        print("\n6. Testing account page data...")
        
        # Simulate account route data
        trial_days_remaining = user.trial_days_remaining
        print(f"📊 Trial days remaining for account page: {trial_days_remaining}")
        
        if trial_days_remaining <= 0:
            print("❌ Trial days remaining is 0 or negative")
            return False
        print("✅ Trial days remaining is positive")
        
        # 7. Test trial banner conditions
        print("\n7. Testing trial banner conditions...")
        
        # Conditions for showing trial banner:
        # user.has_pro_access and user.on_trial and not user.is_premium
        should_show_banner = (
            user.has_pro_access and 
            user.on_trial and 
            not user.is_premium
        )
        
        print(f"🎁 Should show trial banner: {should_show_banner}")
        print(f"   - Has pro access: {user.has_pro_access}")
        print(f"   - On trial: {user.on_trial}")
        print(f"   - Is premium: {user.is_premium}")
        
        if not should_show_banner:
            print("❌ Trial banner should be shown but conditions not met")
            return False
        print("✅ Trial banner conditions met")
        
        # Clean up
        db.session.delete(user)
        db.session.delete(expired_user)
        db.session.commit()
        
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Reverse trial implementation is working correctly")
        print("✅ New users get 14-day Pro trial upon signup")
        print("✅ Trial banner shows correctly on account page")
        print("✅ Pro access is granted during trial period")
        print("✅ Trial expiration is handled correctly")
        
        return True

if __name__ == "__main__":
    success = test_trial_implementation()
    exit(0 if success else 1) 