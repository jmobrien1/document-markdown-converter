#!/usr/bin/env python3
"""
Script to create a production user with API key for Render deployment
"""
import os
import sys
from app import create_app
from app.models import User, db

def create_production_user(email, password):
    """Create a production user with API key"""
    app = create_app()
    
    with app.app_context():
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        
        if existing_user:
            # Regenerate API key if needed
            if not existing_user.api_key:
                existing_user.generate_api_key()
                db.session.commit()
            print(f"✅ Found existing user with API key: {existing_user.api_key}")
            return existing_user.api_key
        
        # Create new user
        user = User(
            email=email,
            is_premium=True,  # Give Pro access
            current_tier='pro'  # Set to pro tier
        )
        user.password = password
        user.generate_api_key()
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Created production user with API key: {user.api_key}")
        return user.api_key

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 create_production_user.py <email> <password>")
        print("Example: python3 create_production_user.py admin@example.com mypassword123")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    api_key = create_production_user(email, password)
    print(f"\n🔑 Production API Key: {api_key}")
    print(f"📧 Email: {email}")
    print(f"🔑 Use this API key in your requests:")
    print(f"X-API-Key: {api_key}") 