# app/__init__.py
# Flask application factory with complete initialization including Celery and conditional blueprint registration

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from celery import Celery

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
celery = Celery(__name__)

def create_app(config_name='default'):
    """
    Application factory with conditional blueprint registration.
    Full app for web service, minimal app for worker service.
    """
    app = Flask(__name__)
    
    # Load configuration
    from config import config
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
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
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Determine if this is a worker context
    is_worker_context = os.environ.get('MDRAFT_SERVICE_TYPE') == 'worker'
    
    # Always register main blueprint (needed for both web and worker)
    from .main import main
    app.register_blueprint(main)
    
    # Only register auth blueprint for web service (not worker)
    if not is_worker_context:
        try:
            # Test if stripe is available before registering auth blueprint
            import stripe
            from .auth import auth
            app.register_blueprint(auth)
            app.logger.info("Auth blueprint registered with stripe support")
        except ImportError:
            app.logger.warning("Stripe not available - auth blueprint not registered")
            # For web service, we could register a limited auth blueprint here
            # that doesn't have payment features
    else:
        app.logger.info("Worker context detected - skipping auth blueprint registration")

    # User Loader (only if auth blueprint is registered)
    if not is_worker_context:
        from .models import User
        @login_manager.user_loader
        def load_user(user_id):
            return User.query.get(int(user_id))

    # Custom CLI command to create the database tables
    @app.cli.command("create-db")
    def create_db_command():
        """Runs the SQL CREATE statements to create the tables."""
        db.create_all()
        print("Database tables created.")

    return app

def create_worker_app(config_name='default'):
    """
    Minimal app factory specifically for Celery workers.
    Does NOT register auth blueprint to avoid stripe dependency.
    """
    # Set environment flag for worker context
    os.environ['MDRAFT_SERVICE_TYPE'] = 'worker'
    
    app = Flask(__name__)
    
    # Load configuration
    from config import config
    app.config.from_object(config[config_name])
    
    # Initialize only essential extensions
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
    
    # Register only main blueprint (no auth = no stripe)
    from .main import main
    app.register_blueprint(main)
    
    app.logger.info("Worker app created with minimal blueprint registration")
    
    return app