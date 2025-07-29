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
from ..services.conversion_service import ConversionService
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
    Handles file upload and conversion using the ConversionService.
    Lightweight route handler that delegates business logic to the service layer.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    # Check if the user requested a pro conversion
    use_pro_converter = request.form.get('pro_conversion') == 'on'
    
    # Get user info
    user = None
    if current_user and current_user.is_authenticated:
        user = User.get_user_safely(current_user.id)
        if user:
            user = db.session.merge(user)
    
    # Use the ConversionService to handle all business logic
    conversion_service = ConversionService()
    success, result = conversion_service.process_conversion(
        file=file,
        filename=file.filename,
        use_pro_converter=use_pro_converter,
        user=user
    )
    
    if not success:
        return jsonify({'error': result}), 400
    
    return jsonify(result), 200

@main.route('/status/<job_id>')
def task_status(job_id):
    """
    Get the status of a conversion task.
    Uses ConversionService for business logic.
    """
    try:
        # For now, we'll use the existing Celery task status
        # In a full implementation, you might want to store task status in the database
        from celery.result import AsyncResult
        task_result = AsyncResult(job_id)
        
        if task_result.ready():
            if task_result.successful():
                return jsonify({
                    'status': 'completed',
                    'job_id': job_id
                })
            else:
                return jsonify({
                    'status': 'failed',
                    'error': str(task_result.result),
                    'job_id': job_id
                })
        else:
            return jsonify({
                'status': 'processing',
                'job_id': job_id
            })
            
    except Exception as e:
        current_app.logger.error(f"Error getting task status: {e}")
        return jsonify({'error': 'Error retrieving task status'}), 500

@main.route('/result/<job_id>')
def task_result(job_id):
    """
    Get the result of a completed conversion task.
    Uses ConversionService for business logic.
    """
    try:
        from celery.result import AsyncResult
        task_result = AsyncResult(job_id)
        
        if not task_result.ready():
            return jsonify({'error': 'Task not completed yet'}), 202
        
        if not task_result.successful():
            return jsonify({'error': str(task_result.result)}), 400
        
        result = task_result.result
        if isinstance(result, dict) and result.get('status') == 'SUCCESS':
            return jsonify({
                'status': 'success',
                'markdown': result.get('markdown', ''),
                'filename': result.get('filename', '')
            })
        else:
            return jsonify({'error': 'Task completed but no result available'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error getting task result: {e}")
        return jsonify({'error': 'Error retrieving task result'}), 500

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