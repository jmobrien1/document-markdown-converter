import os

# Set environment variable to prevent circular imports
os.environ['CELERY_WORKER_RUNNING'] = 'true'

# Import the celery instance
from app import celery, create_app

# Create Flask app and push context
app = create_app()
app.app_context().push()

# The celery instance is already configured with Flask app context
# No additional setup needed