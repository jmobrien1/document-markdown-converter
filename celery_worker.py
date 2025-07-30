from app import create_app, make_celery

# Create Flask app
app = create_app()

# Create Celery instance with Flask app context
celery = make_celery(app)

# Push app context for worker
app.app_context().push()