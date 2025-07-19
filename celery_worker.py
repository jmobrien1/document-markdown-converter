# celery_worker.py
# Worker-specific entry point with minimal Flask context
# This version creates a minimal app context that avoids loading payment-related dependencies

import os
from dotenv import load_dotenv

# Load environment variables first
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery

# Create minimal Flask app for worker
def create_worker_app():
    """Create a minimal Flask app for worker context - no web routes or auth."""
    app = Flask(__name__)
    
    # Load only essential configuration
    from config import config
    config_name = os.getenv('FLASK_CONFIG') or 'default'
    app.config.from_object(config[config_name])
    
    # Initialize only essential extensions
    from app import db, celery
    db.init_app(app)
    
    # Configure Celery
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    return app

# Create worker-specific app (no auth blueprint = no stripe import)
app = create_worker_app()

# Import celery instance
from app import celery

# Push application context for tasks
app.app_context().push()