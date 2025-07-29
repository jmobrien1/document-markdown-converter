# app/__init__.py
# Enhanced with freemium features, subscription management, and anonymous usage tracking

import os
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
import bcrypt

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

def create_standardized_error_response(message, status_code, error_type=None):
    """Create a standardized JSON error response."""
    response = {
        'status': 'error',
        'message': message,
        'status_code': status_code
    }
    
    if error_type:
        response['error_type'] = error_type
    
    # Add request context if available
    if request:
        response['path'] = request.path
        response['method'] = request.method
    
    return response

def create_app(config_name=None):
    """Application factory function."""
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    from config import config
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Log app startup
    app.logger.info(f"Loading app with config: {config_name}")
    
    # Load environment variables
    env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_file):
        app.logger.info(f"Environment variables loaded from: {env_file}")
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Check database migration status
    try:
        with app.app_context():
            # Check if subscription columns exist
            from sqlalchemy import text
            result = db.session.execute(
                text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'is_admin'
                """)
            ).fetchone()
            if result is None:
                app.logger.warning("Database migration check failed: (sqlite3.OperationalError) no such table: information_schema.columns")
    except Exception as e:
        app.logger.warning(f"Database migration check failed: {e}")
    
    # Check bcrypt availability
    try:
        import bcrypt
        app.logger.info("✅ Pure bcrypt available for password hashing")
    except ImportError:
        app.logger.warning("⚠️ bcrypt not available, password hashing may be limited")
    
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
    
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    # Register global error handlers
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "Bad request - invalid data provided",
                400,
                "bad_request"
            )), 400
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "Access forbidden - insufficient permissions",
                403,
                "forbidden"
            )), 403
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "Resource not found",
                404,
                "not_found"
            )), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Handle 413 Request Entity Too Large errors."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                f"File too large. Maximum size: {app.config.get('MAX_FILE_SIZE', 50*1024*1024) // (1024*1024)}MB",
                413,
                "file_too_large"
            )), 413
        return render_template('errors/413.html'), 413
    
    @app.errorhandler(429)
    def too_many_requests(error):
        """Handle 429 Too Many Requests errors."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "Too many requests - please slow down",
                429,
                "rate_limit_exceeded"
            )), 429
        return render_template('errors/429.html'), 429
    
    @app.errorhandler(500)
    def internal_server_error(error):
        """Handle 500 Internal Server Error."""
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "Internal server error - please try again later",
                500,
                "internal_error"
            )), 500
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle unhandled exceptions."""
        app.logger.error(f"Unhandled exception: {error}")
        
        if request.is_xhr or request.path.startswith('/api/'):
            return jsonify(create_standardized_error_response(
                "An unexpected error occurred",
                500,
                "unexpected_error"
            )), 500
        return render_template('errors/500.html'), 500
    
    return app