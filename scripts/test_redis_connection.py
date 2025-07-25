#!/usr/bin/env python3
"""
Redis Connection Test Script
Test Redis connectivity for debugging connection issues.
"""

import os
import sys
import redis
from urllib.parse import urlparse

def test_redis_connection():
    """Test Redis connection using environment variables."""
    
    # Get Redis URL from environment
    redis_url = os.environ.get('CELERY_BROKER_URL')
    
    if not redis_url:
        print("❌ CELERY_BROKER_URL environment variable not set")
        return False
    
    print(f"🔗 Testing Redis connection to: {redis_url}")
    
    try:
        # Parse the Redis URL
        parsed = urlparse(redis_url)
        
        # Extract connection details
        host = parsed.hostname
        port = parsed.port or 6379
        username = parsed.username
        password = parsed.password
        db = parsed.path.lstrip('/') or '0'
        
        print(f"📍 Host: {host}")
        print(f"🔌 Port: {port}")
        print(f"👤 Username: {username or 'None'}")
        print(f"🔑 Password: {'***' if password else 'None'}")
        print(f"🗄️ Database: {db}")
        
        # Create Redis connection
        if username and password:
            r = redis.Redis(
                host=host, 
                port=port, 
                username=username, 
                password=password, 
                db=int(db),
                decode_responses=True
            )
        elif password:
            r = redis.Redis(
                host=host, 
                port=port, 
                password=password, 
                db=int(db),
                decode_responses=True
            )
        else:
            r = redis.Redis(
                host=host, 
                port=port, 
                db=int(db),
                decode_responses=True
            )
        
        # Test connection
        print("🔄 Testing connection...")
        r.ping()
        print("✅ Redis connection successful!")
        
        # Test basic operations
        print("🔄 Testing basic operations...")
        r.set('test_key', 'test_value')
        value = r.get('test_key')
        r.delete('test_key')
        
        if value == 'test_value':
            print("✅ Redis read/write operations successful!")
        else:
            print("❌ Redis read/write operations failed!")
            return False
        
        return True
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main function."""
    print("🔧 Redis Connection Test")
    print("=" * 40)
    
    success = test_redis_connection()
    
    print("=" * 40)
    if success:
        print("✅ Redis connection test passed!")
        sys.exit(0)
    else:
        print("❌ Redis connection test failed!")
        print("\n💡 Troubleshooting tips:")
        print("1. Check if CELERY_BROKER_URL is set correctly")
        print("2. Verify the Redis service is running")
        print("3. Check network connectivity")
        print("4. Verify credentials if authentication is required")
        sys.exit(1)

if __name__ == "__main__":
    main() 