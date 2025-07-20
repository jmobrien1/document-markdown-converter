# app/__init__.py
# Flask application factory with complete initialization including Celery and conditional blueprint registration

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from flask_migrate import Migrate
from dotenv import load_dotenv
import click

# Load environment variables FIRST - single source of truth
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Initialize extensions
db = SQLAlchemy()
celery = Celery(__name__, include=['app.tasks'])
migrate = Migrate()


def create_app(config_name='default', for_worker=False):
    """
    Standardized application factory - single source of truth for configuration.
    Used by both web service and worker service with identical config loading.

    Args:
        config_name (str): The configuration name to use.
        for_worker (bool): If True, skip web-only components for Celery workers.

    Returns:
        Flask: The Flask application instance.
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
    migrate.init_app(app, db)

    if not for_worker:
        # Import and initialize web-only extensions only when needed
        try:
            from flask_login import LoginManager
            from flask_bcrypt import Bcrypt
        except ImportError as e:
            app.logger.warning(f"Web-only imports failed: {str(e)}")
            return app
        login_manager = LoginManager()
        bcrypt = Bcrypt()
        login_manager.init_app(app)
        bcrypt.init_app(app)

        # Configure Flask-Login
        login_manager.login_view = 'auth.login'
        login_manager.login_message = 'Please log in to access this page.'
        login_manager.login_message_category = 'info'

        # Register Blueprints - main blueprint always registered
        from .main import main
        app.register_blueprint(main)

        # Register auth blueprint - always register directly now
        from .auth import auth
        app.register_blueprint(auth)
        app.logger.info("Auth blueprint registered successfully")

        # Register admin blueprint - for now, use try/except ImportError for consistency
        try:
            from .admin import admin
            app.register_blueprint(admin)
            app.logger.info("Admin blueprint registered successfully")
        except ImportError as e:
            app.logger.warning(f"Admin blueprint registration failed: {str(e)}")

        # User Loader for Flask-Login
        from .models import User
        @login_manager.user_loader
        def load_user(user_id):
            return User.query.get(int(user_id))

    # Configure Celery with standardized settings
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        # Use threads pool for memory efficiency (alternative to gevent)
        worker_pool='threads',
        worker_concurrency=4,  # Number of concurrent tasks
        worker_prefetch_multiplier=1,  # Reduce memory usage
        task_acks_late=True,  # Acknowledge tasks after completion
        task_reject_on_worker_lost=True,  # Requeue tasks if worker dies
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask
    
    # Custom CLI command to create the database tables
    @app.cli.command("create-db")
    def create_db_command():
        """Runs the SQL CREATE statements to create the tables."""
        db.create_all()
        print("Database tables created.")

    # Custom CLI command to migrate Stripe columns
    @app.cli.command("migrate-stripe")
    def migrate_stripe_columns():
        """Add missing Stripe columns to users table."""
        from sqlalchemy import text
        
        try:
            # Check if columns exist first
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('stripe_customer_id', 'stripe_subscription_id', 'is_admin')
            """))
            existing_columns = [row[0] for row in result]
            
            if 'is_admin' not in existing_columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
                print("✅ Added is_admin column")
            else:
                print("✅ is_admin column already exists")
            
            if 'stripe_customer_id' not in existing_columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)"))
                print("✅ Added stripe_customer_id column")
            else:
                print("✅ stripe_customer_id column already exists")
            
            if 'stripe_subscription_id' not in existing_columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255)"))
                print("✅ Added stripe_subscription_id column")
            else:
                print("✅ stripe_subscription_id column already exists")
            
            db.session.commit()
            print("🎉 All columns migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise

    # Custom CLI command to add admin privileges to a user
    @app.cli.command("add-admin")
    @click.argument("email")
    def add_admin_command(email):
        """Grant admin privileges to a user by email."""
        from .models import User
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_admin = True
            db.session.commit()
            print(f"Successfully granted admin privileges to {email}.")
        else:
            print(f"User with email '{email}' not found.")

    return app