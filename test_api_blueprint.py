#!/usr/bin/env python3
"""
Test script to check API blueprint registration
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_api_blueprint():
    """Test if the API blueprint can be created"""
    try:
        print("🔍 Testing API blueprint creation...")
        
        # Test the lazy import
        from app.api import get_api_blueprint
        print("✅ get_api_blueprint imported successfully")
        
        # Test creating the blueprint
        api_blueprint = get_api_blueprint()
        print("✅ API blueprint created successfully")
        print(f"📋 Blueprint name: {api_blueprint.name}")
        print(f"📋 Blueprint url_prefix: {api_blueprint.url_prefix}")
        print(f"📋 Number of routes: {len(api_blueprint.deferred_functions)}")
        
        # List all routes
        print("📋 Routes:")
        for rule in api_blueprint.url_map.iter_rules():
            print(f"  - {rule.rule} [{', '.join(rule.methods)}]")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating API blueprint: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_creation():
    """Test if the Flask app can be created"""
    try:
        print("\n🔍 Testing Flask app creation...")
        
        from app import create_app
        print("✅ create_app imported successfully")
        
        app = create_app()
        print("✅ Flask app created successfully")
        
        # Check if API routes are registered
        api_routes = []
        for rule in app.url_map.iter_rules():
            if rule.rule.startswith('/api/v1/'):
                api_routes.append(rule.rule)
        
        print(f"📋 Found {len(api_routes)} API routes:")
        for route in api_routes:
            print(f"  - {route}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating Flask app: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing API Blueprint Registration")
    print("=" * 50)
    
    # Test API blueprint creation
    blueprint_ok = test_api_blueprint()
    
    # Test Flask app creation
    app_ok = test_app_creation()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"✅ API Blueprint: {'PASS' if blueprint_ok else 'FAIL'}")
    print(f"✅ Flask App: {'PASS' if app_ok else 'FAIL'}")
    
    if blueprint_ok and app_ok:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.") 