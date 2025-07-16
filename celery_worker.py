# celery_worker.py
# This script is the entry point for the Celery worker.
# This version explicitly loads the .env file to ensure the worker has all credentials.

import os
from dotenv import load_dotenv

# --- THE FIX ---
# Explicitly find and load the .env file at the very beginning of the worker's life.
# This ensures all environment variables, like GOOGLE_APPLICATION_CREDENTIALS,
# are available before any other code is imported.
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
# --- END FIX ---

from app import create_app, celery

# Create a Flask app instance using the app factory
# This is crucial for the worker to have access to app.config
app = create_app(os.getenv('FLASK_CONFIG') or 'default')

# Push an application context to make it available for the tasks
app.app_context().push()
