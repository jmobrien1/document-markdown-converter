# config.py
import os
import json
import tempfile
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-dev-key-for-local-testing')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'txt', 'html',
        'htm', 'csv', 'json', 'xml', 'epub'
    }

    # Anonymous user daily conversion limit
    ANONYMOUS_DAILY_LIMIT = 5

    # --- Celery Configuration ---
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # --- Google Cloud Storage Configuration ---
    GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')

    # Handle Google Cloud credentials for both local development and Render deployment
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        # Render deployment - create temporary credentials file from environment variable
        try:
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            temp_creds = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            temp_creds.write(credentials_json)
            temp_creds.close()
            GCS_CREDENTIALS_PATH = temp_creds.name
        except Exception as e:
            print(f"Error creating credentials file: {e}")
            GCS_CREDENTIALS_PATH = None
    else:
        # Local development - use file path
        GCS_CREDENTIALS_PATH = os.path.join(basedir, 'gcs-credentials.json')
        if not os.path.exists(GCS_CREDENTIALS_PATH):
            GCS_CREDENTIALS_PATH = None

    # --- Google Document AI Configuration ---
    DOCAI_PROCESSOR_REGION = os.environ.get('DOCAI_PROCESSOR_REGION', 'us-east4')
    DOCAI_PROCESSOR_ID = os.environ.get('DOCAI_PROCESSOR_ID')

    # --- Stripe Configuration ---
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

    # --- Database Configuration ---
    # Use PostgreSQL in production (Render), SQLite in development
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        # Production database (Render provides DATABASE_URL)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        # Handle SQLAlchemy 1.4+ compatibility
        if DATABASE_URL.startswith('postgres://'):
            SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    else:
        # Development database
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, '..', 'app.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def init_app(app):
        """Performs application-initialization tasks."""
        if not app.config.get('GCS_BUCKET_NAME'):
            app.logger.warning("GCS_BUCKET_NAME is not set. File uploads will fail.")
        if not app.config.get('DOCAI_PROCESSOR_ID'):
            app.logger.warning("DOCAI_PROCESSOR_ID is not set. Pro conversions will fail.")
        if not app.config.get('GCS_CREDENTIALS_PATH'):
            app.logger.warning("GCS credentials not configured. All GCS operations will fail.")
        if not app.config.get('STRIPE_SECRET_KEY'):
            app.logger.warning("STRIPE_SECRET_KEY is not set. Payments will fail.")


class DevelopmentConfig(Config):
    """Configuration settings for the development environment."""
    DEBUG = True


class ProductionConfig(Config):
    """Configuration settings for the production environment."""
    DEBUG = False

    # Production-specific settings
    SQLALCHEMY_ECHO = False

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        import logging
        import sys
        from pythonjsonlogger import jsonlogger
        from flask import has_request_context, request

        class CustomJsonFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)
                log_record['timestamp'] = self.formatTime(record, self.datefmt)
                log_record['level'] = record.levelname
                log_record['message'] = record.getMessage()
                if has_request_context():
                    log_record['path'] = request.path
                    log_record['method'] = request.method

        if os.environ.get('FLASK_CONFIG') == 'production':
            # Remove all handlers associated with the app logger object
            for handler in list(app.logger.handlers):
                app.logger.removeHandler(handler)
            handler = logging.StreamHandler(sys.stdout)
            formatter = CustomJsonFormatter()
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            app.logger.addHandler(handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('mdraft startup (JSON logger enabled)')


# A dictionary to easily access configuration classes by name.
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}