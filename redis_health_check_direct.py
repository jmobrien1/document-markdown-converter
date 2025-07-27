#!/usr/bin/env python3
"""
Direct Redis Health Check Script
This script can be run directly from the project root.
"""

import os
import sys
from datetime import datetime, timezone

def main():
    print(f"[{datetime.now(timezone.utc)}] Starting redis_health_check task...")
    
    try:
        import redis
        import os
        
        # Try to get Redis URL from environment variables first
        redis_url = os.environ.get('CELERY_BROKER_URL')
        
        if not redis_url:
            # Fallback to app config
            try:
                from app import create_app
                app = create_app('production')
                with app.app_context():
                    redis_url = app.config.get('CELERY_BROKER_URL')
            except Exception as e:
                print(f"Could not load app config: {e}")
                return False
        
        if not redis_url:
            print("No Redis URL configured, skipping health check")
            return True
            
            try:
                print(f"Attempting to connect to Redis: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")
                
                # Use redis.from_url for better URL parsing
                r = redis.from_url(redis_url, decode_responses=True)
                
                # Test connection
                r.ping()
                
                # Get connection info
                info = r.info()
                
                result = {
                    'status': 'healthy',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'message': 'Redis health check completed',
                    'redis_version': info.get('redis_version', 'unknown'),
                    'connected_clients': info.get('connected_clients', 0)
                }
                
                print(f"Redis health check successful: {result}")
                return True
                    
            except redis.ConnectionError as e:
                print(f"Redis connection error: {e}")
                return False
            except Exception as e:
                print(f"Redis health check error: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Error running Redis health check: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 