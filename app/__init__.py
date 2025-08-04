# app/__init__.py
# Enhanced with freemium features, subscription management, and anonymous usage tracking

import os
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
import bcrypt

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()

# Initialize Celery at module level to avoid circular imports
from celery import Celery

# Create base celery instance
celery = Celery('mdraft', include=['app.tasks'])

def make_celery(app):
    """Create Celery instance and configure it with Flask app context."""
    # Configure Celery with Flask app config using new format
    celery.conf.update(
        result_backend=app.config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        broker_url=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

def create_app(config_name=None):
    """Application factory pattern for Flask app creation."""
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')
    
    app.logger.info(f"Loading app with config: {config_name}")
    
    # Import and apply configuration
    from config import config
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Initialize Flask-Login inside create_app to avoid circular dependency
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))
    
    # Configure bcrypt
    try:
        import bcrypt
        app.logger.info("✅ Pure bcrypt available for password hashing")
    except ImportError:
        app.logger.warning("⚠️ bcrypt not available, using fallback")
    
    # Register blueprints
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    app.logger.info("Auth blueprint registered successfully")
    
    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    app.logger.info("Admin blueprint registered successfully")
    
    from .api_docs import api_docs as api_docs_blueprint
    app.register_blueprint(api_docs_blueprint, url_prefix='/api/docs')
    app.logger.info("API documentation blueprint registered successfully")
    
    from .uploads import uploads as uploads_blueprint
    app.register_blueprint(uploads_blueprint, url_prefix='/uploads')
    app.logger.info("Uploads blueprint registered successfully")
    
    from .api import get_api_blueprint
    api_blueprint = get_api_blueprint()
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')
    app.logger.info("API blueprint registered successfully")
    
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    app.logger.info("Main blueprint registered successfully")
    
    # Configure Celery with Flask app context
    make_celery(app)
    
    # Check database migration status
    try:
        with app.app_context():
            # Check if subscription columns exist using database-appropriate method
            from sqlalchemy import text
            if db.engine.dialect.name == 'sqlite':
                # Use SQLite-compatible PRAGMA table_info
                result = db.session.execute(
                    text("PRAGMA table_info(users)")
                ).fetchall()
                has_is_admin = any(row[1] == 'is_admin' for row in result)
                if not has_is_admin:
                    app.logger.warning("Database migration check: is_admin column not found in users table")
            else:
                # Use information_schema for PostgreSQL and other databases
                result = db.session.execute(
                    text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'users' AND column_name = 'is_admin'
                    """)
                ).fetchone()
                if not result:
                    app.logger.warning("Database migration check: is_admin column not found in users table")
    except Exception as e:
        app.logger.warning(f"Database migration check failed: {e}")
    
    return app

# Create celery instance for worker
# Initialize celery at module level to avoid circular imports
celery = Celery('mdraft', include=['app.tasks'])

# Only create the Flask app when not running as a Celery worker
if not os.environ.get('CELERY_WORKER_RUNNING'):
    app = create_app()
    make_celery(app)