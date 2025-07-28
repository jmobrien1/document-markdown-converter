#!/usr/bin/env python3
"""
Test script to verify the DetachedInstanceError fix.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def test_session_fix():
    """Test that the session fix works properly."""
    app = create_app()
    
    with app.app_context():
        # Find a user to test with
        user = User.query.first()
        if not user:
            print("❌ No users found in database. Please create a user first.")
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
                
                return True
                
            except Exception as e:
                print(f"❌ Error accessing user relationships: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error in get_user_safely: {e}")
            return False

if __name__ == "__main__":
    print("🔧 Testing session fix for DetachedInstanceError")
    print("=" * 60)
    
    success = test_session_fix()
    
    if success:
        print("=" * 60)
        print("🎉 Session fix test passed!")
        print("The DetachedInstanceError should now be resolved.")
    else:
        print("=" * 60)
        print("❌ Session fix test failed.")
        print("There may still be issues with the session handling.") 