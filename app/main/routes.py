# app/main/routes.py
# Enhanced with freemium logic, anonymous usage tracking, batch processing support, and health checks

import os
import uuid
import tempfile
import json
import struct
from datetime import datetime, timezone
from google.cloud import storage
from google.api_core import exceptions as google_exceptions
from flask import (
    render_template, request, jsonify, url_for, current_app, session
)
from werkzeug.utils import secure_filename
from app.tasks import convert_file_task

# Conditional Flask-Login import for web environment
try:
    from flask_login import current_user
except ImportError:
    current_user = None

from ..models import User, AnonymousUsage, Conversion
from .. import db
from . import main

# File signature definitions for magic number validation
FILE_SIGNATURES = {
    # PDF files
    'pdf': [b'%PDF'],
    
    # Microsoft Office files
    'doc': [b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'],  # OLE2 compound document
    'docx': [b'PK\x03\x04'],  # ZIP archive (Office Open XML)
    'xlsx': [b'PK\x03\x04'],  # ZIP archive (Office Open XML)
    'pptx': [b'PK\x03\x04'],  # ZIP archive (Office Open XML)
    
    # Image files
    'png': [b'\x89PNG\r\n\x1a\n'],
    'jpg': [b'\xFF\xD8\xFF'],
    'jpeg': [b'\xFF\xD8\xFF'],
    'gif': [b'GIF87a', b'GIF89a'],
    'bmp': [b'BM'],
    'tiff': [b'II*\x00', b'MM\x00*'],
    'tif': [b'II*\x00', b'MM\x00*'],
    'webp': [b'RIFF'],
    
    # Text files
    'txt': [],  # No specific signature, will be validated by content analysis
    'html': [b'<!DOCTYPE', b'<html', b'<HTML'],
    'htm': [b'<!DOCTYPE', b'<html', b'<HTML'],
    
    # Other supported formats
    'csv': [],  # No specific signature
    'json': [b'{', b'['],  # JSON starts with { or [
    'xml': [b'<?xml', b'<xml'],
    'zip': [b'PK\x03\x04'],
    'epub': [b'PK\x03\x04'],  # EPUB is a ZIP archive
}

def validate_file_signature(file_stream, filename):
    """
    Validate file signature (magic number) against file extension.
    
    Args:
        file_stream: File stream object
        filename: Original filename with extension
        
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Get file extension
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_extension not in FILE_SIGNATURES:
            return False, f"Unsupported file type: {file_extension}"
        
        # Read first 8 bytes for signature checking
        file_stream.seek(0)
        header = file_stream.read(8)
        file_stream.seek(0)  # Reset position
        
        # Get expected signatures for this file type
        expected_signatures = FILE_SIGNATURES.get(file_extension, [])
        
        # If no specific signature is defined (like for .txt), accept the file
        if not expected_signatures:
            return True, None
        
        # Check if any of the expected signatures match
        for signature in expected_signatures:
            if header.startswith(signature):
                return True, None
        
        # If we get here, no signature matched
        return False, f"File signature does not match extension. Expected {file_extension} format."
        
    except Exception as e:
        current_app.logger.error(f"Error validating file signature: {e}")
        return False, "Error validating file format"

def validate_file_content(file_stream, filename):
    """
    Additional content validation for text-based files.
    
    Args:
        file_stream: File stream object
        filename: Original filename with extension
        
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # For text files, check if content is readable
        if file_extension in ['txt', 'csv', 'json', 'xml', 'html', 'htm']:
            file_stream.seek(0)
            content = file_stream.read(1024)  # Read first 1KB
            
            # Check if content is readable text (not binary)
            try:
                content.decode('utf-8')
            except UnicodeDecodeError:
                return False, f"File appears to be binary, not valid {file_extension} content"
            
            # For JSON files, validate JSON structure
            if file_extension == 'json':
                try:
                    json.loads(content.decode('utf-8'))
                except json.JSONDecodeError:
                    return False, "Invalid JSON format"
            
            file_stream.seek(0)  # Reset position
            return True, None
        
        return True, None
        
    except Exception as e:
        current_app.logger.error(f"Error validating file content: {e}")
        return False, "Error validating file content"

def allowed_file(filename):
    """Check if the file's extension is in the allowed set."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def check_conversion_limits():
    """Check if user/session can perform conversions."""
    if current_user and current_user.is_authenticated:
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

def get_accurate_pdf_page_count(file_stream, filename):
    """
    Get accurate PDF page count using pypdf library.
    
    Args:
        file_stream: File stream object
        filename (str): Original filename
        
    Returns:
        int: Actual number of pages in the PDF, or 1 for non-PDF files
    """
    try:
        # Only count pages for PDF files
        if not filename.lower().endswith('.pdf'):
            return 1
            
        # Import pypdf for accurate page counting
        from pypdf import PdfReader
        
        # Use pypdf to get accurate page count
        file_stream.seek(0)  # Reset to beginning
        pdf_reader = PdfReader(file_stream)
        page_count = len(pdf_reader.pages)
        current_app.logger.info(f"Accurate PDF page count for {filename}: {page_count} pages")
        return page_count
        
    except ImportError:
        current_app.logger.error("pypdf library not available - this should not happen in production")
        raise Exception("PDF page counting library not available. Please contact support.")
    except Exception as e:
        current_app.logger.error(f"Error getting PDF page count for {filename}: {e}")
        raise Exception(f"Error reading PDF file: {str(e)}")

@main.route('/')
def index():
    """Renders the main page with the file upload form."""
    # Get usage info for anonymous users
    if not current_user or not current_user.is_authenticated:
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
    Enhanced with comprehensive file validation and security checks.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or no selected file'}), 400

    # SECURITY: Comprehensive file validation
    try:
        # Validate file signature (magic number)
        is_valid_signature, signature_error = validate_file_signature(file, file.filename)
        if not is_valid_signature:
            current_app.logger.warning(f"File signature validation failed: {signature_error} for file: {file.filename}")
            return jsonify({'error': signature_error}), 400
        
        # Validate file content for text-based files
        is_valid_content, content_error = validate_file_content(file, file.filename)
        if not is_valid_content:
            current_app.logger.warning(f"File content validation failed: {content_error} for file: {file.filename}")
            return jsonify({'error': content_error}), 400
        
        # Log successful validation
        current_app.logger.info(f"File validation passed for: {file.filename}")
        
    except Exception as e:
        current_app.logger.error(f"Error during file validation: {e}")
        return jsonify({'error': 'Error validating file format'}), 400

    # Check conversion limits
    can_convert, limit_error = check_conversion_limits()
    if not can_convert:
        return jsonify({'error': limit_error}), 429

    filename = secure_filename(file.filename)
    blob_name = f"uploads/{uuid.uuid4()}_{filename}"
    bucket_name = current_app.config['GCS_BUCKET_NAME']

    # Check if the user requested a pro conversion
    use_pro_converter = request.form.get('pro_conversion') == 'on'
    
    # Get user info for logging and Pro access check
    user_email = 'Anonymous'
    user = None
    if current_user and current_user.is_authenticated:
        user = User.get_user_safely(current_user.id)
        if user:
            # Ensure user is properly bound to session
            user = db.session.merge(user)
            user_email = user.email
        else:
            user_email = 'Unknown'
    
    # Block Pro conversions for users without access
    if use_pro_converter:
        if not current_user or not current_user.is_authenticated:
            return jsonify({
                'error': 'Pro conversions require a free account. Please sign up to access advanced features.',
                'upgrade_required': True,
                'upgrade_url': url_for('auth.signup')
            }), 403
        
        if not user or not user.has_pro_access:
            # Check if user has trial days remaining
            trial_days = user.trial_days_remaining if user else 0
            if trial_days > 0:
                return jsonify({
                    'error': f'Your trial has expired. You had {trial_days} days remaining. Please upgrade to continue using Pro features.',
                    'upgrade_required': True,
                    'upgrade_url': url_for('auth.upgrade'),
                    'trial_expired': True
                }), 403
            else:
                return jsonify({
                    'error': 'Pro conversions require an active subscription or trial. Please upgrade to access advanced features.',
                    'upgrade_required': True,
                    'upgrade_url': url_for('auth.upgrade')
                }), 403
    
    current_app.logger.info(f"Convert route called. Pro conversion: {use_pro_converter}, User: {user_email}")
    
    try:
        # Validate credentials before queuing task
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path:
            current_app.logger.error("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
            return jsonify({'error': 'Google Cloud credentials not configured. Please contact support.'}), 500
        
        if not os.path.exists(credentials_path):
            current_app.logger.error(f"Google Cloud credentials file not found at: {credentials_path}")
            return jsonify({'error': 'Google Cloud credentials file not found. Please contact support.'}), 500
        
        # Read and validate credentials content
        try:
            with open(credentials_path, 'r') as f:
                credentials_content = f.read()
            
            if not credentials_content.strip():
                current_app.logger.error("Google Cloud credentials file is empty")
                return jsonify({'error': 'Google Cloud credentials file is empty. Please contact support.'}), 500
            
            # Basic JSON validation
            import json
            try:
                json.loads(credentials_content)
                current_app.logger.info("Google Cloud credentials validated successfully")
            except json.JSONDecodeError as e:
                current_app.logger.error(f"Google Cloud credentials file contains invalid JSON: {e}")
                return jsonify({'error': 'Google Cloud credentials file contains invalid JSON. Please contact support.'}), 500
                
        except Exception as e:
            current_app.logger.error(f"Error reading Google Cloud credentials: {e}")
            return jsonify({'error': 'Error reading Google Cloud credentials. Please contact support.'}), 500

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
    user_id = current_user.id if current_user and current_user.is_authenticated else None
    session_id = session.get('session_id') if not current_user or not current_user.is_authenticated else None
    
    # Get file size and accurate page count
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    # Get accurate page count for PDF files
    page_count = get_accurate_pdf_page_count(file, filename)
    
    # Determine if this will be a batch job based on actual page count
    is_large_file = page_count > 10  # Google DocAI sync API limit
    
    # Create conversion record with proper error handling
    try:
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
    except Exception as e:
        db.session.rollback()  # Clean up the failed transaction
        if 'job_id' in str(e) and 'does not exist' in str(e):
            print(f"❌ Database schema error: job_id column missing. Error: {str(e)}")
            return jsonify({
                'error': 'System maintenance in progress. Please try again in a few minutes.',
                'details': 'Database schema is being updated.'
            }), 503
        else:
            print(f"❌ Database error during conversion creation: {str(e)}")
            return jsonify({'error': 'Database error occurred. Please try again.'}), 500

    # Update anonymous usage
    if not current_user or not current_user.is_authenticated:
        usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
        usage.increment_usage()

    # Start the conversion task with accurate page count
    task = convert_file_task.delay(
        bucket_name,
        blob_name,
        filename,
        use_pro_converter,
        conversion.id,
        page_count  # Pass accurate page count to the task
    )

    # Store the Celery job ID in the Conversion record
    try:
        conversion.job_id = task.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()  # Clean up the failed transaction
        if 'job_id' in str(e) and 'does not exist' in str(e):
            print(f"⚠️ Warning: job_id column missing, but conversion {conversion.id} was created successfully")
            # Continue without job_id - the conversion will still work
        else:
            print(f"❌ Error storing job_id: {str(e)}")
            # Continue without job_id - the conversion will still work

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
    Returns lightweight status information only - no large payloads.
    """
    task = convert_file_task.AsyncResult(job_id)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state, 
            'status': 'Pending...',
            'progress': 0
        }
    elif task.state == 'PROGRESS':
        progress_info = task.info.get('status', 'Processing...')
        progress_percent = task.info.get('progress', 0) if isinstance(task.info, dict) else 0
        response = {
            'state': task.state, 
            'status': progress_info,
            'progress': progress_percent
        }
    elif task.state == 'SUCCESS':
        # Only return lightweight success info - no large markdown content
        result_info = task.info if task.info else {}
        response = {
            'state': 'SUCCESS',
            'status': 'Conversion completed successfully',
            'progress': 100,
            'filename': result_info.get('filename', 'Unknown'),
            'markdown_length': len(result_info.get('markdown', '')) if result_info.get('markdown') else 0,
            'has_result': True
        }
    else: # 'FAILURE'
        error_info = task.info if task.info else {}
        response = {
            'state': 'FAILURE',
            'status': 'Conversion failed',
            'progress': 0,
            'error': error_info.get('error', 'An unknown error occurred.') if isinstance(error_info, dict) else str(error_info)
        }
        
    return jsonify(response)

@main.route('/result/<job_id>')
def task_result(job_id):
    """
    Endpoint to retrieve the full conversion result (including markdown content).
    Only called when status indicates SUCCESS.
    """
    task = convert_file_task.AsyncResult(job_id)
    
    if task.state != 'SUCCESS':
        return jsonify({
            'error': 'Result not ready yet. Check status first.',
            'state': task.state
        }), 400
    
    # Return the full result with markdown content
    result_info = task.info if task.info else {}
    response = {
        'state': 'SUCCESS',
        'markdown': result_info.get('markdown', ''),
        'filename': result_info.get('filename', 'Unknown'),
        'status': result_info.get('status', 'SUCCESS')
    }
    
    return jsonify(response)

@main.route('/stats')
def conversion_stats():
    """Get conversion statistics for dashboard."""
    try:
        if current_user.is_authenticated:
            # Ensure we have a fresh user object bound to the session
            user = User.get_user_safely(current_user.id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # User-specific stats using the fresh user object
            total_conversions = user.conversions.count()
            daily_conversions = user.get_daily_conversions()
            successful_conversions = user.conversions.filter_by(status='completed').count()
            
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
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user's conversion history using the fresh user object
        conversions = user.conversions.order_by(
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
            'total_conversions': user.conversions.count(),
            'daily_conversions': user.get_daily_conversions()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting conversion history: {str(e)}")
        return jsonify({'error': 'Error retrieving history'}), 500

# (Removed /health, /health/web, and /health/worker routes; now in app/health/routes.py)

@main.route('/pricing')
def pricing():
    """Display tiered pricing page."""
    subscription_tiers = current_app.config.get('SUBSCRIPTION_TIERS', {})
    return render_template('pricing.html', subscription_tiers=subscription_tiers)

@main.app_errorhandler(413)
def request_entity_too_large(e):
    """Custom error handler for 413 Request Entity Too Large."""
    max_size_mb = current_app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify(error=f"File is too large. Maximum size is {max_size_mb:.0f}MB."), 413