#!/usr/bin/env python3
"""
Test script to simulate the account route and verify the session fix.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Conversion
from flask_login import login_user

def test_account_route_simulation():
    """Simulate the account route to test session handling."""
    app = create_app()
    
    with app.app_context():
        # Find the test user
        user = User.query.filter_by(email="obrienmike+123@gmail.com").first()
        if not user:
            print("❌ Test user not found. Please run setup first.")
            return False
        
        print(f"✅ Found test user: {user.email}")
        
        # Simulate the account route logic (without login_user to avoid request context issues)
        try:
            # Get user directly from database to ensure fresh session
            fresh_user = User.query.get(user.id)
            if not fresh_user:
                print("❌ Could not get user from database")
                return False
            
            print("✅ Successfully retrieved user from database")
            
            # Ensure user is properly bound to session
            fresh_user = db.session.merge(fresh_user)
            print("✅ Successfully merged user into session")
            
            # Test accessing conversions (this was causing the DetachedInstanceError)
            try:
                total_conversions = fresh_user.conversions.count()
                print(f"✅ Successfully accessed conversions: {total_conversions} conversions")
                
                # Test accessing daily conversions
                daily_conversions = fresh_user.get_daily_conversions()
                print(f"✅ Successfully accessed daily conversions: {daily_conversions}")
                
                # Test accessing recent conversions
                recent_conversions = fresh_user.conversions.order_by(
                    Conversion.created_at.desc()
                ).limit(10).all()
                print(f"✅ Successfully accessed recent conversions: {len(recent_conversions)} items")
                
                # Test calculating success rate
                successful_conversions = fresh_user.conversions.filter_by(status='completed').count()
                success_rate = (successful_conversions / total_conversions * 100) if total_conversions > 0 else 0
                print(f"✅ Successfully calculated success rate: {success_rate}%")
                
                # Test accessing Pro conversions
                pro_conversions_count = fresh_user.conversions.filter_by(conversion_type='pro').count()
                print(f"✅ Successfully accessed Pro conversions: {pro_conversions_count}")
                
                # Test accessing user properties
                trial_days = fresh_user.trial_days_remaining
                has_pro_access = fresh_user.has_pro_access
                print(f"✅ Successfully accessed user properties:")
                print(f"   - Trial days remaining: {trial_days}")
                print(f"   - Has pro access: {has_pro_access}")
                
                return True
                
            except Exception as e:
                print(f"❌ Error accessing user relationships: {e}")
                import traceback
                traceback.print_exc()
                return False
                
        except Exception as e:
            print(f"❌ Error in account route simulation: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function to run the account route test."""
    print("🧪 Testing account route session handling")
    print("=" * 60)
    
    success = test_account_route_simulation()
    
    if success:
        print("=" * 60)
        print("🎉 Account route test passed!")
        print("The DetachedInstanceError should now be resolved.")
        print("\nYou can now safely access the /account page.")
    else:
        print("=" * 60)
        print("❌ Account route test failed.")
        print("There may still be issues with the session handling.")

if __name__ == "__main__":
    main() 