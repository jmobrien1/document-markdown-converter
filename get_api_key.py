#!/usr/bin/env python3
"""
Script to get a valid API key for testing
"""
import os
import sys
from app import create_app
from app.models import User, db

def get_or_create_api_key():
    """Get or create a test API key"""
    app = create_app()
    
    with app.app_context():
        # Check if test user exists
        test_user = User.query.filter_by(email='test@example.com').first()
        
        if not test_user:
            # Create test user
            test_user = User(
                email='test@example.com',
                is_premium=True,  # Give Pro access
                current_tier='pro'  # Set to pro tier
            )
            test_user.password = 'password123'  # Use the password setter
            test_user.generate_api_key()
            db.session.add(test_user)
            db.session.commit()
            print(f"✅ Created test user with API key: {test_user.api_key}")
        else:
            # Regenerate API key if needed
            if not test_user.api_key:
                test_user.generate_api_key()
                db.session.commit()
            print(f"✅ Found existing test user with API key: {test_user.api_key}")
        
        print(f"\n📋 Test User Details:")
        print(f"Email: {test_user.email}")
        print(f"API Key: {test_user.api_key}")
        print(f"Pro Access: {test_user.has_pro_access}")
        print(f"Current Tier: {test_user.current_tier}")
        print(f"\n🔑 Use this API key in your requests:")
        print(f"X-API-Key: {test_user.api_key}")

if __name__ == '__main__':
    get_or_create_api_key() 