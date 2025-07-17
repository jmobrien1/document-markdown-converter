# config.py
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))

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
    
    # --- THE FIX: Explicitly load the path to the credentials file ---
    GCS_CREDENTIALS_PATH = os.path.join(basedir, '..', os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', ''))

    # --- Google Document AI Configuration ---
    DOCAI_PROCESSOR_REGION = os.environ.get('DOCAI_PROCESSOR_REGION', 'us-east4') 
    DOCAI_PROCESSOR_ID = os.environ.get('DOCAI_PROCESSOR_ID')

    # --- Database Configuration ---
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def init_app(app):
        """Performs application-initialization tasks."""
        if not app.config.get('GCS_BUCKET_NAME'):
            app.logger.warning("GCS_BUCKET_NAME is not set. File uploads will fail.")
        if not app.config.get('DOCAI_PROCESSOR_ID'):
            app.logger.warning("DOCAI_PROCESSOR_ID is not set. Pro conversions will fail.")
        if not app.config.get('GCS_CREDENTIALS_PATH') or not os.path.exists(app.config['GCS_CREDENTIALS_PATH']):
            app.logger.warning("GCS credentials file not found. All GCS operations will fail.")


class DevelopmentConfig(Config):
    """Configuration settings for the development environment."""
    DEBUG = True


class ProductionConfig(Config):
    """Configuration settings for the production environment."""
    DEBUG = False
    # In production, you would typically use a managed PostgreSQL or MySQL database
    # and load its URL from the DATABASE_URL environment variable.
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


# A dictionary to easily access configuration classes by name.
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}