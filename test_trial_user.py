#!/usr/bin/env python3
"""
Test script to create a trial user and verify the implementation
"""

from app import create_app, db
from app.models import User
from datetime import datetime, timedelta, timezone

def create_test_user():
    """Create a test user to verify trial implementation."""
    
    app = create_app()
    with app.app_context():
        # Create a test user
        test_email = "test-trial@example.com"
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=test_email).first()
        if existing_user:
            print(f"User {test_email} already exists, deleting...")
            db.session.delete(existing_user)
            db.session.commit()
        
        # Create new user with trial
        user = User(email=test_email)
        user.password = "testpassword123"
        
        # Set trial dates (14-day trial)
        user.trial_start_date = datetime.now(timezone.utc)
        user.trial_end_date = user.trial_start_date + timedelta(days=14)
        user.on_trial = True
        
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Test user created: {test_email}")
        print(f"🎁 Trial start: {user.trial_start_date}")
        print(f"🎁 Trial end: {user.trial_end_date}")
        print(f"⏰ Days remaining: {user.trial_days_remaining}")
        print(f"💎 Has pro access: {user.has_pro_access}")
        
        return user

if __name__ == "__main__":
    user = create_test_user() 