import os
import logging
from datetime import timedelta

class Config:
    """Base configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'rtf'}
    
    # Google Cloud Storage Configuration
    GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
    GCS_CREDENTIALS_JSON = os.environ.get('GCS_CREDENTIALS_JSON')
    
    # Google Document AI Configuration
    DOCAI_PROCESSOR_ID = os.environ.get('DOCAI_PROCESSOR_ID')
    
    # Stripe Configuration
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Celery Configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
    CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 minutes
    CELERY_TASK_TIME_LIMIT = 600  # 10 minutes
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    
    # RAG Service Configuration
    ENABLE_RAG = os.environ.get('ENABLE_RAG', 'false').lower() == 'true'
    RAG_MODEL = os.environ.get('RAG_MODEL', 'all-MiniLM-L6-v2')
    RAG_MAX_TOKENS = int(os.environ.get('RAG_MAX_TOKENS', '500'))
    RAG_CHUNK_OVERLAP = int(os.environ.get('RAG_CHUNK_OVERLAP', '50'))
    RAG_ENABLED = os.environ.get('RAG_ENABLED', 'false').lower() == 'true'
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    @staticmethod
    def init_app(app):
        """Initialize application configuration"""
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, app.config['LOG_LEVEL']),
            format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        
        # Log configuration warnings
        if not app.config['GCS_BUCKET_NAME']:
            app.logger.warning("GCS_BUCKET_NAME is not set. File uploads will fail.")
        
        if not app.config['DOCAI_PROCESSOR_ID']:
            app.logger.warning("DOCAI_PROCESSOR_ID is not set. Pro conversions will fail.")
        
        if not app.config['GCS_CREDENTIALS_JSON']:
            app.logger.warning("GCS credentials not configured. All GCS operations will fail.")
        
        if not app.config['STRIPE_SECRET_KEY']:
            app.logger.warning("STRIPE_SECRET_KEY is not set. Payments will fail.")
        
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            app.logger.warning("Email configuration not set. Email notifications will fail.")
        
        # Log RAG configuration
        if app.config['ENABLE_RAG']:
            app.logger.info(f"RAG service enabled with model: {app.config['RAG_MODEL']}")
        else:
            app.logger.info("RAG service disabled")
        
        if app.config['OPENAI_API_KEY']:
            app.logger.info("OpenAI API key configured")
        else:
            app.logger.warning("OPENAI_API_KEY not set. LLM features will fail.")

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Production-specific logging
        import logging
        from logging.handlers import RotatingFileHandler
        import os
        
        if not app.debug and not app.testing:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler('logs/mdraft.log', maxBytes=10240, backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('mdraft startup')

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 