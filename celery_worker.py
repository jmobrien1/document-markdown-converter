#!/usr/bin/env python
"""
Celery worker startup script.
This script creates a Flask application instance and starts the Celery worker
with the proper application context.
"""

import os
import sys

# Ensure the app directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Flask app factory and Celery configuration
try:
    from app import create_app, make_celery
    print("Successfully imported Flask app factory")
except ImportError as e:
    print(f"Error importing Flask app: {e}")
    sys.exit(1)

# Create Flask application instance with proper config
config_name = os.getenv('FLASK_CONFIG', 'development')
print(f"Creating Flask app with config: {config_name}")

try:
    flask_app = create_app(config_name)
    print("Flask app created successfully")
except Exception as e:
    print(f"Error creating Flask app: {e}")
    sys.exit(1)

# Create and configure Celery with Flask app context
try:
    celery = make_celery(flask_app)
    print("Celery configured successfully")
except Exception as e:
    print(f"Error configuring Celery: {e}")
    sys.exit(1)

# Push application context so Celery tasks can access Flask extensions
try:
    app_context = flask_app.app_context()
    app_context.push()
    print("Flask application context pushed successfully")
    
    # Test that Flask-Login is available
    from flask_login import current_user
    print("Flask-Login is available in worker context")
    
except Exception as e:
    print(f"Error setting up Flask context: {e}")
    sys.exit(1)

# Import tasks to ensure they're registered
try:
    from app import tasks
    print("Tasks imported successfully")
except ImportError as e:
    print(f"Warning: Could not import tasks: {e}")

if __name__ == '__main__':
    print("Starting Celery worker...")
    celery.start()