# app/__init__.py
# Flask application factory with complete initialization including Celery and conditional blueprint registration

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from flask_migrate import Migrate
from flask_mail import Mail
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
mail = Mail()




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
    mail.init_app(app)
    
    # Ensure database schema is up to date
    with app.app_context():
        try:
            from sqlalchemy import text
            # Check if is_admin column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'is_admin'
            """))
            if not result.fetchone():
                db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
                db.session.commit()
                app.logger.info("✅ Added is_admin column to users table")
        except Exception as e:
            app.logger.warning(f"Database migration check failed: {str(e)}")
            # Continue anyway - the migration command will handle it

    if not for_worker:
        # Import and initialize web-only extensions only when needed
        try:
            from flask_login import LoginManager
        except ImportError as e:
            app.logger.warning(f"Web-only imports failed: {str(e)}")
            return app
        login_manager = LoginManager()
        login_manager.init_app(app)
        
        app.logger.info("✅ Pure bcrypt available for password hashing")

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

        # Register health blueprint
        from app.health import health as health_blueprint
        app.register_blueprint(health_blueprint)

        # Register API blueprint
        from app.api import api as api_blueprint
        app.register_blueprint(api_blueprint, url_prefix='/api/v1')

        # Register API documentation blueprint
        try:
            from app.api_docs import api_docs as api_docs_blueprint
            app.register_blueprint(api_docs_blueprint, url_prefix='/api/v1/docs')
            app.logger.info("API documentation blueprint registered successfully")
        except ImportError as e:
            app.logger.warning(f"API documentation blueprint registration failed: {str(e)}")

        # Register uploads blueprint
        try:
            from .uploads import uploads as uploads_blueprint
            app.register_blueprint(uploads_blueprint, url_prefix='/uploads')
            app.logger.info("Uploads blueprint registered successfully")
        except ImportError as e:
            app.logger.warning(f"Uploads blueprint registration failed: {str(e)}")
            # Try alternative import paths
            try:
                import sys
                import os
                # Add the app directory to Python path
                app_dir = os.path.dirname(__file__)
                if app_dir not in sys.path:
                    sys.path.insert(0, app_dir)
                # Try direct import
                from uploads import uploads as uploads_blueprint
                app.register_blueprint(uploads_blueprint, url_prefix='/uploads')
                app.logger.info("Uploads blueprint registered successfully (alternative path)")
            except ImportError as e2:
                app.logger.warning(f"Uploads blueprint alternative registration failed: {str(e2)}")
                # Try creating a minimal blueprint as fallback
                try:
                    from flask import Blueprint
                    fallback_uploads = Blueprint('uploads', __name__)
                    @fallback_uploads.route('/batch-uploader')
                    def fallback_batch_uploader():
                        return "Uploads blueprint not available", 503
                    app.register_blueprint(fallback_uploads, url_prefix='/uploads')
                    app.logger.info("Uploads blueprint registered with fallback")
                except Exception as e3:
                    app.logger.warning(f"Uploads blueprint fallback registration failed: {str(e3)}")

        # User Loader for Flask-Login
        from .models import User
        @login_manager.user_loader
        def load_user(user_id):
            try:
                return User.get_user_safely(int(user_id))
            except Exception as e:
                # If all else fails, rollback and return None (user not found)
                from flask import current_app
                current_app.logger.error(f"Failed to load user {user_id}: {str(e)}")
                try:
                    from . import db
                    db.session.rollback()
                except:
                    pass
                return None

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
        
        print("🔍 Starting database migration check...")
        
        try:
            # First, check if the users table exists
            result = db.session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'users'
                )
            """))
            table_exists = result.fetchone()[0]
            
            if not table_exists:
                print("❌ Users table does not exist. Creating tables...")
                db.create_all()
                print("✅ Tables created successfully")
                return
            
            print("✅ Users table exists")
            
            # Check if columns exist first
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('stripe_customer_id', 'stripe_subscription_id', 'is_admin')
            """))
            existing_columns = [row[0] for row in result]
            print(f"📋 Existing columns: {existing_columns}")
            
            if 'is_admin' not in existing_columns:
                print("🔧 Adding is_admin column...")
                db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
                print("✅ Added is_admin column")
            else:
                print("✅ is_admin column already exists")
            
            if 'stripe_customer_id' not in existing_columns:
                print("🔧 Adding stripe_customer_id column...")
                db.session.execute(text("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)"))
                print("✅ Added stripe_customer_id column")
            else:
                print("✅ stripe_customer_id column already exists")
            
            if 'stripe_subscription_id' not in existing_columns:
                print("🔧 Adding stripe_subscription_id column...")
                db.session.execute(text("ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255)"))
                print("✅ Added stripe_subscription_id column")
            else:
                print("✅ stripe_subscription_id column already exists")
            
            db.session.commit()
            print("🎉 All columns migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {str(e)}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise

    if not for_worker:
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

        @app.cli.command("check-database-schema")
        def check_database_schema_command():
            """Check database schema health and report issues."""
            from sqlalchemy import text
            try:
                print("🔍 Checking database schema...")
                
                # Check if conversions table exists
                result = db.session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'conversions'
                    )
                """))
                table_exists = result.fetchone()[0]
                print(f"✅ conversions table exists: {table_exists}")
                
                if table_exists:
                    # Check for required columns
                    required_columns = ['id', 'user_id', 'original_filename', 'status', 'created_at', 'job_id']
                    for column in required_columns:
                        result = db.session.execute(text(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'conversions' AND column_name = '{column}'
                        """))
                        exists = result.fetchone() is not None
                        status = "✅" if exists else "❌"
                        print(f"{status} {column} column exists: {exists}")
                
                print("🔍 Database schema check complete!")
                
            except Exception as e:
                print(f"❌ Error checking database schema: {str(e)}")
                raise

    return app