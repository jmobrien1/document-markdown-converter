# app/main/routes.py
# Enhanced with freemium logic, anonymous usage tracking, batch processing support, and health checks

import os
import uuid
import tempfile
import json
from datetime import datetime
from google.cloud import storage
from google.api_core import exceptions as google_exceptions
from flask import (
    render_template, request, jsonify, url_for, current_app, session
)
from werkzeug.utils import secure_filename
from app.tasks import convert_file_task
from flask_login import current_user
from ..models import User, AnonymousUsage, Conversion
from .. import db
from . import main

def allowed_file(filename):
    """Check if the file's extension is in the allowed set."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def check_conversion_limits():
    """Check if user/session can perform conversions."""
    if current_user.is_authenticated:
        # Logged-in users have unlimited conversions
        return True, None
    
    # Check anonymous user limits
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    
    usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
    daily_limit = current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
    
    if not usage.can_convert(daily_limit):
        return False, f"Daily limit reached. Anonymous users can convert {daily_limit} files per day. Please sign up for unlimited conversions."
    
    return True, None

def get_storage_client():
    """Get Google Cloud Storage client with proper credential handling."""
    try:
        # Check for environment variable credentials (Render deployment)
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            # Create temporary credentials file from environment variable
            temp_creds = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            temp_creds.write(credentials_json)
            temp_creds.close()
            current_app.logger.info(f"Using credentials from environment variable, temp file: {temp_creds.name}")
            return storage.Client.from_service_account_json(temp_creds.name)
        
        # Check for local credentials file (local development)
        local_creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'gcs-credentials.json')
        if os.path.exists(local_creds_path):
            current_app.logger.info(f"Using local credentials file: {local_creds_path}")
            return storage.Client.from_service_account_json(local_creds_path)
        
        # Try default credentials (if running on GCP)
        current_app.logger.info("Attempting to use default credentials")
        return storage.Client()
        
    except Exception as e:
        current_app.logger.error(f"Failed to create storage client: {e}")
        raise Exception(f"Could not authenticate with Google Cloud Storage: {e}")

@main.route('/')
def index():
    """Renders the main page with the file upload form."""
    # Get usage info for anonymous users
    if not current_user.is_authenticated:
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
        
        usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
        daily_limit = current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
        remaining_conversions = max(0, daily_limit - usage.conversions_today)
    else:
        remaining_conversions = None  # Unlimited for logged-in users
    
    return render_template('index.html', 
                         remaining_conversions=remaining_conversions,
                         daily_limit=current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5))

@main.route('/convert', methods=['POST'])
def convert():
    """
    Handles file upload, checks for pro conversion flag, and starts the task.
    Now supports both authenticated and anonymous users with rate limiting.
    Enhanced for batch processing of large documents.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or no selected file'}), 400

    # Check conversion limits
    can_convert, limit_error = check_conversion_limits()
    if not can_convert:
        return jsonify({'error': limit_error}), 429

    filename = secure_filename(file.filename)
    blob_name = f"uploads/{uuid.uuid4()}_{filename}"
    bucket_name = current_app.config['GCS_BUCKET_NAME']

    # Check if the user requested a pro conversion
    use_pro_converter = request.form.get('pro_conversion') == 'on'
    
    current_app.logger.info(f"Convert route called. Pro conversion: {use_pro_converter}, User: {current_user.email if current_user.is_authenticated else 'Anonymous'}")
    
    try:
        # Get storage client with proper credential handling
        storage_client = get_storage_client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_file(file)
        current_app.logger.info(f"Successfully uploaded {filename} to GCS bucket {bucket_name}")

    except Exception as e:
        current_app.logger.error(f"GCS Upload Failed: {e}")
        return jsonify({'error': 'Could not upload file to cloud storage.'}), 500

    # Create conversion record
    user_id = current_user.id if current_user.is_authenticated else None
    session_id = session.get('session_id') if not current_user.is_authenticated else None
    
    # Get file size
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    # Estimate if this will be a batch job (for user feedback)
    is_large_file = file_size > 1750000  # ~25 pages * 70KB = ~1.75MB
    
    conversion = Conversion(
        user_id=user_id,
        session_id=session_id,
        original_filename=filename,
        file_size=file_size,
        file_type=os.path.splitext(filename)[1].lower(),
        conversion_type='pro' if use_pro_converter else 'standard',
        status='pending'
    )
    db.session.add(conversion)
    db.session.commit()

    # Update anonymous usage
    if not current_user.is_authenticated:
        usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
        usage.increment_usage()

    # Start the conversion task
    task = convert_file_task.delay(
        bucket_name,
        blob_name,
        filename,
        use_pro_converter
    )

    # Provide appropriate user feedback based on file size
    response_data = {
        'job_id': task.id,
        'conversion_id': conversion.id,
        'status_url': url_for('main.task_status', job_id=task.id),
        'is_large_file': is_large_file
    }
    
    if is_large_file and use_pro_converter:
        response_data['message'] = 'Large document detected. This may take several minutes to process.'
    
    return jsonify(response_data), 202

@main.route('/status/<job_id>')
def task_status(job_id):
    """
    Endpoint for the client to poll for the status of a background task.
    Enhanced to show progress for batch processing.
    """
    task = convert_file_task.AsyncResult(job_id)
    
    if task.state == 'PENDING':
        response = {'state': task.state, 'status': 'Pending...'}
    elif task.state == 'PROGRESS':
        response = {'state': task.state, 'status': task.info.get('status', 'Processing...')}
    elif task.state == 'SUCCESS':
        response = {'state': 'SUCCESS', 'result': task.info}
    else: # 'FAILURE'
        response = {
            'state': 'FAILURE',
            'status': str(task.info),
            'error': task.info.get('error', 'An unknown error occurred.')
        }
        
    return jsonify(response)

@main.route('/stats')
def conversion_stats():
    """Get conversion statistics for dashboard."""
    try:
        if current_user.is_authenticated:
            # User-specific stats
            total_conversions = current_user.conversions.count()
            daily_conversions = current_user.get_daily_conversions()
            successful_conversions = current_user.conversions.filter_by(status='completed').count()
            
            # Calculate success rate
            success_rate = (successful_conversions / total_conversions * 100) if total_conversions > 0 else 0
            
            return jsonify({
                'authenticated': True,
                'total_conversions': total_conversions,
                'daily_conversions': daily_conversions,
                'successful_conversions': successful_conversions,
                'success_rate': round(success_rate, 1),
                'can_convert': True
            })
        else:
            # Anonymous user stats
            session_id = session.get('session_id')
            if session_id:
                usage = AnonymousUsage.query.filter_by(session_id=session_id).first()
                if usage:
                    daily_limit = current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
                    remaining = max(0, daily_limit - usage.conversions_today)
                    return jsonify({
                        'authenticated': False,
                        'daily_conversions': usage.conversions_today,
                        'daily_limit': daily_limit,
                        'remaining_conversions': remaining,
                        'can_convert': usage.can_convert()
                    })
            
            daily_limit = current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
            return jsonify({
                'authenticated': False,
                'daily_conversions': 0,
                'daily_limit': daily_limit,
                'remaining_conversions': daily_limit,
                'can_convert': True
            })
            
    except Exception as e:
        current_app.logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': 'Error retrieving statistics'}), 500

@main.route('/history')
def conversion_history():
    """Get conversion history for current user."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # Get user's conversion history
        conversions = current_user.conversions.order_by(
            Conversion.created_at.desc()
        ).limit(50).all()
        
        history = []
        for conv in conversions:
            history.append({
                'id': conv.id,
                'filename': conv.original_filename,
                'file_type': conv.file_type,
                'conversion_type': conv.conversion_type,
                'status': conv.status,
                'created_at': conv.created_at.isoformat(),
                'completed_at': conv.completed_at.isoformat() if conv.completed_at else None,
                'processing_time': conv.processing_time,
                'file_size': conv.file_size,
                'markdown_length': conv.markdown_length,
                'error_message': conv.error_message
            })
        
        return jsonify({
            'history': history,
            'total_conversions': current_user.conversions.count(),
            'daily_conversions': current_user.get_daily_conversions()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting conversion history: {str(e)}")
        return jsonify({'error': 'Error retrieving history'}), 500

# --- Health Check Endpoints ---

@main.route('/health')
def health_check():
    """General health check endpoint for monitoring service status."""
    try:
        # Test database connection
        from ..models import User
        User.query.first()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Test Redis connection (Celery broker)
    try:
        from .. import celery
        celery.control.ping(timeout=1.0)
        celery_status = "healthy"
    except Exception as e:
        celery_status = f"unhealthy: {str(e)}"
    
    # Check if this is worker or web
    service_type = "web"
    
    # Test stripe import (should work on web, might fail on worker)
    stripe_available = False
    try:
        import stripe
        stripe_available = True
    except ImportError:
        pass
    
    health_data = {
        "service": service_type,
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "celery": celery_status,
        "stripe_available": stripe_available,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    status_code = 200 if health_data["status"] == "healthy" else 503
    return jsonify(health_data), status_code

@main.route('/health/web')
def health_web():
    """Web service health check endpoint."""
    health_data = {
        "service": "web",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {}
    }
    
    # Test database connection
    try:
        from ..models import User
        User.query.first()
        health_data["dependencies"]["database"] = "healthy"
    except Exception as e:
        health_data["dependencies"]["database"] = f"unhealthy: {str(e)}"
        health_data["status"] = "degraded"
    
    # Test stripe availability
    try:
        import stripe
        health_data["dependencies"]["stripe"] = "available"
    except ImportError:
        health_data["dependencies"]["stripe"] = "not_available"
        health_data["status"] = "degraded"
    
    # Test redis/celery connection
    try:
        from .. import celery
        celery.control.ping(timeout=1.0)
        health_data["dependencies"]["celery"] = "healthy"
    except Exception as e:
        health_data["dependencies"]["celery"] = f"unhealthy: {str(e)}"
    
    status_code = 200 if health_data["status"] == "healthy" else 503
    return jsonify(health_data), status_code

@main.route('/health/worker')
def health_worker():
    """Worker service health check endpoint."""
    health_data = {
        "service": "worker",
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {}
    }
    
    # Test that we can import worker dependencies
    try:
        from app.tasks import convert_file_task
        health_data["dependencies"]["tasks"] = "available"
    except Exception as e:
        health_data["dependencies"]["tasks"] = f"unavailable: {str(e)}"
        health_data["status"] = "unhealthy"
    
    # Test celery worker status
    try:
        from .. import celery
        inspect = celery.control.inspect()
        stats = inspect.stats()
        active_workers = len(stats) if stats else 0
        health_data["dependencies"]["active_workers"] = active_workers
        
        if active_workers == 0:
            health_data["status"] = "no_workers"
            
    except Exception as e:
        health_data["dependencies"]["celery_inspect"] = f"failed: {str(e)}"
        health_data["status"] = "unhealthy"
    
    # Check if stripe is available (should NOT be required for worker)
    try:
        import stripe
        health_data["dependencies"]["stripe"] = "available_but_not_needed"
    except ImportError:
        health_data["dependencies"]["stripe"] = "not_available_as_expected"
    
    status_code = 200 if health_data["status"] in ["healthy", "no_workers"] else 503
    return jsonify(health_data), status_code

@main.app_errorhandler(413)
def request_entity_too_large(e):
    """Custom error handler for 413 Request Entity Too Large."""
    max_size_mb = current_app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify(error=f"File is too large. Maximum size is {max_size_mb:.0f}MB."), 413