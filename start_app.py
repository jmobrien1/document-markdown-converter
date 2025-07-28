#!/usr/bin/env python3
"""
Script to start the Flask app for testing.
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

def main():
    """Start the Flask app."""
    app = create_app()
    
    print("🚀 Starting Flask app for testing...")
    print("=" * 50)
    print("📋 Test Account Details:")
    print("   Email: obrienmike+123@gmail.com")
    print("   Password: testpassword123")
    print("   Status: Pro user with full access")
    print("=" * 50)
    print("🌐 App will be available at: http://localhost:5000")
    print("📱 You can now:")
    print("   1. Sign in with the test account")
    print("   2. Visit /account to test the session fix")
    print("   3. Test Pro features")
    print("   4. Try batch processing")
    print("   5. Test multi-format exports")
    print("=" * 50)
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Start the app in debug mode
    app.run(debug=True, host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main() 