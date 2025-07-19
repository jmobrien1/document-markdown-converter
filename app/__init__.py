# app/__init__.py - Standardized Configuration Loading
# Single source of truth for all configuration loading

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from celery import Celery
from dotenv import load_dotenv

# Load environment variables FIRST - single source of truth
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
celery = Celery(__name__)

def create_app(config_name='default'):
    """
    Standardized application factory - single source of truth for configuration.
    Used by both web service and worker service with identical config loading.
    """
    app = Flask(__name__)
    
    # Load configuration using standardized method
    from config import config
    app.config.from_object(config[config_name])
    
    # Log configuration source for debugging
    app.logger.info(f"Loading app with config: {config_name}")
    app.logger.info(f"Environment variables loaded from: {dotenv_path}")
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    # Configure Celery with standardized settings
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
    
    # Register Blueprints - main blueprint always registered
    from .main import main
    app.register_blueprint(main)
    
    # Register auth blueprint - this is where stripe imports happen
    try:
        from .auth import auth
        app.register_blueprint(auth)
        app.logger.info("Auth blueprint registered successfully")
    except ImportError as e:
        app.logger.warning(f"Auth blueprint registration failed: {str(e)}")
        app.logger.warning("This is expected for worker services if stripe is not available")

    # User Loader for Flask-Login
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