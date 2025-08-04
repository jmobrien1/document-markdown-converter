#!/usr/bin/env python3
"""
Script to test API key functionality
"""
import os
import sys
from app import create_app
from app.models import User, db

def test_api_key(api_key):
    """Test if an API key is valid"""
    app = create_app()
    
    with app.app_context():
        # Find user by API key
        user = User.query.filter_by(api_key=api_key).first()
        
        if not user:
            print(f"❌ API key not found: {api_key}")
            return False
        
        print(f"✅ API key found for user: {user.email}")
        print(f"📧 Email: {user.email}")
        print(f"🔑 API Key: {user.api_key}")
        print(f"👑 Pro Access: {user.has_pro_access}")
        print(f"🎯 Current Tier: {user.current_tier}")
        
        # Test if user has Pro access
        if user.has_pro_access:
            print("✅ User has Pro access - API key should work!")
            return True
        else:
            print("❌ User does not have Pro access - API key will be rejected")
            return False

def list_all_users():
    """List all users with their API keys"""
    app = create_app()
    
    with app.app_context():
        users = User.query.all()
        
        if not users:
            print("❌ No users found in database")
            return
        
        print(f"📋 Found {len(users)} users:")
        for user in users:
            print(f"  - Email: {user.email}")
            print(f"    API Key: {user.api_key}")
            print(f"    Pro Access: {user.has_pro_access}")
            print(f"    Current Tier: {user.current_tier}")
            print()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Test specific API key
        api_key = sys.argv[1]
        test_api_key(api_key)
    else:
        # List all users
        list_all_users() 