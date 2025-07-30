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
    # Configure Celery with Flask app config
    celery.conf.update(app.config)
    
    # Set up task routing
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
    
    app.config.from_object(f'config.{config_name.capitalize()}Config')
    app.logger.info(f"Loading app with config: {config_name}")
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Initialize Flask-Login inside create_app to avoid circular imports
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))
    
    # Check bcrypt availability
    try:
        bcrypt.hashpw(b'test', bcrypt.gensalt())
        app.logger.info("✅ Pure bcrypt available for password hashing")
    except Exception as e:
        app.logger.warning(f"⚠️ bcrypt not available: {e}")
    
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
    
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    app.logger.info("Main blueprint registered successfully")
    
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
                ).fetchall()
                if not result:
                    app.logger.warning("Database migration check: is_admin column not found in users table")
    except Exception as e:
        app.logger.warning(f"Database migration check failed: {e}")
    
    return app

# Create Flask app and configure celery
app = create_app()
celery = make_celery(app)