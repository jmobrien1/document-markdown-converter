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
        from app import create_app
        import redis
        
        app = create_app('production')
        
        with app.app_context():
            # Get Redis connection from app config
            redis_url = app.config.get('CELERY_BROKER_URL')
            if not redis_url:
                print("No Redis URL configured, skipping health check")
                return True
            
            try:
                # Parse Redis URL and connect
                if redis_url.startswith('redis://'):
                    # Extract host and port from URL
                    url_parts = redis_url.replace('redis://', '').split('/')[0]
                    if '@' in url_parts:
                        # Format: redis://username:password@host:port
                        auth_part, host_part = url_parts.split('@')
                        host, port = host_part.split(':')
                    else:
                        # Format: redis://host:port
                        host, port = url_parts.split(':')
                    
                    port = int(port)
                    
                    # Connect to Redis
                    r = redis.Redis(host=host, port=port, decode_responses=True)
                    
                    # Test connection
                    r.ping()
                    
                    result = {
                        'status': 'healthy',
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'message': 'Redis health check completed',
                        'host': host,
                        'port': port
                    }
                    
                    print(f"Redis health check successful: {result}")
                    return True
                    
                else:
                    print(f"Unsupported Redis URL format: {redis_url}")
                    return False
                    
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