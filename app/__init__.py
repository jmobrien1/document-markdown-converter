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
    """Configure the existing Celery instance with Flask app context."""
    # Configure Celery with Flask app config using new format
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        broker_pool_limit=1,
        broker_connection_max_retries=3,
        broker_heartbeat=None,
        worker_prefetch_multiplier=1,
        worker_cancel_long_running_tasks_on_connection_loss=True,
        task_acks_late=True,
        result_expires=1800,
        timezone='UTC',
        enable_utc=True,
        broker_transport_options={
            'visibility_timeout': 18000
        }
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
    
    # Configure Celery BEFORE registering blueprints
    make_celery(app)
    
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
    
    # Startup validation and dependency checks
    app.logger.info("🔍 Starting dependency validation...")
    
    # Check RAG dependencies
    rag_dependencies_available = True
    try:
        import tiktoken
        # Conditional import to avoid NumPy/PyTorch issues
        if os.environ.get('DISABLE_ML_IMPORTS', 'false').lower() != 'true':
            import sentence_transformers
            from annoy import AnnoyIndex
            app.logger.info("✅ RAG dependencies available")
        else:
            app.logger.info("✅ RAG dependencies disabled via environment variable")
    except ImportError as e:
        app.logger.warning(f"⚠️ RAG dependencies not available: {e}")
        rag_dependencies_available = False
    except Exception as e:
        app.logger.warning(f"⚠️ RAG dependencies failed to load: {e}")
        rag_dependencies_available = False
    
    # Check OpenAI
    openai_key_from_config = app.config.get('OPENAI_API_KEY')
    openai_key_from_env = os.environ.get('OPENAI_API_KEY')
    app.logger.info(f"🔍 OpenAI API Key Debug:")
    app.logger.info(f"   From config: {'SET' if openai_key_from_config else 'NOT SET'}")
    app.logger.info(f"   From env: {'SET' if openai_key_from_env else 'NOT SET'}")
    app.logger.info(f"   Config value: {openai_key_from_config[:10] + '...' if openai_key_from_config else 'None'}")
    app.logger.info(f"   Env value: {openai_key_from_env[:10] + '...' if openai_key_from_env else 'None'}")
    
    openai_available = bool(openai_key_from_config or openai_key_from_env)
    if openai_available:
        app.logger.info("✅ OpenAI API key configured")
    else:
        app.logger.warning("⚠️ OpenAI API key not configured")
    
    # Check database
    try:
        with app.app_context():
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
        app.logger.info("✅ Database connection available")
    except Exception as e:
        app.logger.warning(f"⚠️ Database connection failed: {e}")
    
    # Check Redis/Celery
    try:
        from celery import current_app as celery_app
        celery_app.control.inspect().active()
        app.logger.info("✅ Celery/Redis connection available")
    except Exception as e:
        app.logger.warning(f"⚠️ Celery/Redis connection failed: {e}")
    
    # Store dependency status in app config
    app.config['RAG_DEPENDENCIES_AVAILABLE'] = rag_dependencies_available
    app.config['OPENAI_AVAILABLE'] = openai_available
    
    app.logger.info("🎯 Dependency validation complete")
    
    # Register blueprints AFTER Celery is configured
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
    
    app.logger.info("🚀 Application startup complete")
    return app