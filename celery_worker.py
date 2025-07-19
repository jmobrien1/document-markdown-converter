# celery_worker.py
# Worker-specific entry point that completely avoids stripe dependencies

import os
from dotenv import load_dotenv

# Load environment variables first
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Set service type BEFORE importing anything from app
os.environ['MDRAFT_SERVICE_TYPE'] = 'worker'

# Now import app factory and create worker-specific app
from app import create_worker_app, celery

# Create minimal worker app (no auth blueprint = no stripe)
app = create_worker_app(os.getenv('FLASK_CONFIG') or 'default')

# Push application context for tasks
app.app_context().push()

# Log successful worker startup
app.logger.info("Celery worker started successfully without stripe dependencies")