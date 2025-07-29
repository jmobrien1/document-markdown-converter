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
        # Document AI (Pro) supported formats
        'pdf', 'gif', 'tiff', 'tif', 'jpg', 'jpeg', 'png', 'bmp', 'webp', 'html',
        # Markitdown (Standard) supported formats  
        'docx', 'xlsx', 'xls', 'pptx', 'htm', 'csv', 'json', 'xml', 'zip', 'epub'
    }

    # --- File Upload Configuration ---
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    ANONYMOUS_DAILY_LIMIT = 5
    ANONYMOUS_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB for anonymous users
    
    # --- Trial and Subscription Configuration ---
    TRIAL_DAYS = 14
    TRIAL_PAGES_PER_MONTH = 100
    PRO_PAGES_PER_MONTH = 1000
    ENTERPRISE_PAGES_PER_MONTH = -1  # Unlimited
    
    # --- Conversion Limits ---
    BATCH_PROCESSING_PAGE_THRESHOLD = 10  # Use batch processing for PDFs > 10 pages
    BATCH_PROCESSING_TIMEOUT = 600  # 10 minutes
    SYNCHRONOUS_PROCESSING_TIMEOUT = 300  # 5 minutes
    
    # --- Security Configuration ---
    VIRUS_SCAN_ENABLED = os.environ.get('VIRUS_SCAN_ENABLED', 'false').lower() == 'true'
    CLAMD_HOST = os.environ.get('CLAMD_HOST', 'localhost')
    CLAMD_PORT = int(os.environ.get('CLAMD_PORT', 3310))
    
    # --- Google Cloud Configuration ---
    GOOGLE_CLOUD_PROJECT = os.environ.get('GOOGLE_CLOUD_PROJECT')
    GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
    DOCAI_PROCESSOR_REGION = os.environ.get('DOCAI_PROCESSOR_REGION', 'us')
    DOCAI_PROCESSOR_ID = os.environ.get('DOCAI_PROCESSOR_ID')
    DOCAI_PROCESSOR_VERSION = 'pretrained-ocr-v2.0-2023-06-02'
    
    # --- API Configuration ---
    API_RATE_LIMIT = '100 per minute'
    API_RATE_LIMIT_STORAGE_URL = 'memory://'
    
    # --- Session Configuration ---
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 30 * 24 * 60 * 60  # 30 days
    
    # --- Error Handling Configuration ---
    MAX_ERROR_MESSAGE_LENGTH = 500
    LOG_ERROR_DETAILS = os.environ.get('LOG_ERROR_DETAILS', 'true').lower() == 'true'
    
    # --- Anonymous user daily conversion limit
    ANONYMOUS_DAILY_LIMIT = 5

    # --- Celery Configuration ---
    # Use environment variables for Redis connection
    # In production (Render), these will point to the managed Redis service
    # In development, fall back to localhost
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Fix for CPendingDeprecationWarning - explicitly set the new configuration
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    
    # For cron jobs, ensure we have proper Redis configuration
    if not os.environ.get('CELERY_BROKER_URL') and os.environ.get('RENDER'):
        # We're on Render but no Redis URL is set - this is an error
        print("WARNING: CELERY_BROKER_URL not set on Render. Cron jobs may fail.")

    # --- Flask-Mail Configuration ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')

    # --- Google Cloud Storage Configuration ---
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
    # DOCAI_PROCESSOR_REGION = os.environ.get('DOCAI_PROCESSOR_REGION', 'us-east4')
    # DOCAI_PROCESSOR_ID = os.environ.get('DOCAI_PROCESSOR_ID')

    # --- Stripe Configuration ---
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # --- Subscription Tiers Configuration ---
    SUBSCRIPTION_TIERS = {
        'pro': {
            'name': 'Mdraft Pro',
            'price_id': os.environ.get('STRIPE_PRO_PRICE_ID', 'price_pro_placeholder'),
            'monthly_price': '$9.99',
            'features': [
                'Advanced OCR with Google Document AI',
                '1000 pages per month',
                'Batch processing',
                'Priority support',
                'API access',
                'Advanced export formats (JSON, TXT)'
            ]
        },
        'enterprise': {
            'name': 'Mdraft Enterprise',
            'price_id': os.environ.get('STRIPE_ENTERPRISE_PRICE_ID', 'price_enterprise_placeholder'),
            'monthly_price': '$29.99',
            'features': [
                'Everything in Pro',
                'Unlimited pages per month',
                'Custom integrations',
                'Dedicated support',
                'White-label options',
                'Advanced analytics',
                'Team management'
            ]
        }
    }

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

    # --- Flask-Smorest Configuration ---
    API_TITLE = "mdraft.app API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.2"
    OPENAPI_URL_PREFIX = "/api/v1/docs"
    OPENAPI_SWAGGER_UI_PATH = "/"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    API_SPEC_OPTIONS = {
        "info": {
            "title": "mdraft.app API",
            "version": "1.0.0",
            "description": "API for converting documents to Markdown format with advanced OCR capabilities",
            "contact": {
                "name": "mdraft.app Support",
                "url": "https://mdraft.app"
            }
        },
        "servers": [
            {
                "url": "https://mdraft.app/api/v1",
                "description": "Production server"
            },
            {
                "url": "http://localhost:5000/api/v1",
                "description": "Development server"
            }
        ]
    }

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
        if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            app.logger.warning("Email configuration not set. Email notifications will fail.")


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