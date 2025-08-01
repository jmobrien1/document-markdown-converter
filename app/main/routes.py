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
    render_template, request, jsonify, url_for, current_app, session, send_file, abort, flash, redirect, make_response
)
from werkzeug.utils import secure_filename
from app.tasks import convert_file_task

# Conditional Flask-Login import for web environment
try:
    from flask_login import current_user, login_required
except ImportError:
    current_user = None
    login_required = None

from ..models import User, AnonymousUsage, Conversion, Batch, ConversionJob, Team, TeamMember
from ..services.conversion_service import ConversionService
from ..services.conversion_engine import ConversionEngine
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

def reset_file_stream(file_stream):
    """
    Safely reset file stream to beginning.
    
    Args:
        file_stream: File stream object
    """
    try:
        file_stream.seek(0)
    except (OSError, IOError) as e:
        # Handle cases where seek might fail
        print(f"Warning: Could not reset file stream: {e}")

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
        
        # FIXED: Ensure we're at the beginning
        reset_file_stream(file_stream)
        
        # Read first 8 bytes for signature checking
        header = file_stream.read(8)
        
        # CRITICAL: Always reset stream after reading
        reset_file_stream(file_stream)
        
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
        return False, f"Error validating file signature: {str(e)}"

def validate_file_content(file_stream, filename):
    """
    Validate file content for basic security checks.
    
    Args:
        file_stream: File stream object
        filename: Original filename with extension
        
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # FIXED: Ensure we're at the beginning
        reset_file_stream(file_stream)
        
        # Check file size
        file_stream.seek(0, 2)  # Seek to end
        file_size = file_stream.tell()
        
        # CRITICAL: Reset to beginning after size check
        reset_file_stream(file_stream)
        
        max_size = current_app.config.get('MAX_FILE_SIZE', 50 * 1024 * 1024)
        if file_size > max_size:
            return False, f"File too large. Maximum size: {max_size // (1024*1024)}MB"
        
        # Basic content validation for text files
        if filename.lower().endswith('.txt'):
            # Read first 1KB to check for binary content
            sample = file_stream.read(1024)
            
            # CRITICAL: Reset stream after reading sample
            reset_file_stream(file_stream)
            
            # Check if file contains null bytes (binary indicator)
            if b'\x00' in sample:
                return False, "Text file contains binary content"
        
        return True, None
        
    except Exception as e:
        return False, f"Error validating file content: {str(e)}"

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS', {'pdf', 'doc', 'docx', 'txt'})

def check_conversion_limits():
    """Check if user has exceeded conversion limits."""
    if current_user and current_user.is_authenticated:
        # Logged in users have higher limits
        return True, None
    else:
        # Anonymous user - check daily limits
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
        
        usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
        daily_limit = current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
        
        if not usage.can_convert(daily_limit):
            return False, f"Daily conversion limit exceeded. Limit: {daily_limit} conversions per day."
        
        return True, None

def get_storage_client():
    """Get Google Cloud Storage client."""
    try:
        # Check if credentials are available
        credentials_path = current_app.config.get('GCS_CREDENTIALS_PATH')
        if credentials_path and os.path.exists(credentials_path):
            return storage.Client.from_service_account_json(credentials_path)
        else:
            # Try default credentials
            return storage.Client()
    except Exception as e:
        current_app.logger.error(f"Error creating storage client: {e}")
        raise Exception("Failed to initialize cloud storage client")

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
        
        # FIXED: Ensure we're at the beginning
        reset_file_stream(file_stream)
        
        # Use pypdf to get accurate page count
        pdf_reader = PdfReader(file_stream)
        page_count = len(pdf_reader.pages)
        
        # CRITICAL: Reset stream after reading
        reset_file_stream(file_stream)
        
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

@main.route('/test-form')
def test_form():
    """Test page for debugging form submission."""
    return render_template('test_form_submission.html')

@main.route('/convert', methods=['GET', 'POST'])
def convert():
    """
    Handles file upload and conversion.
    GET: Returns method info for debugging
    POST: Processes file conversion using ConversionService
    """
    if request.method == 'GET':
        # Handle GET requests for debugging
        return jsonify({
            'error': 'This endpoint requires a POST request with a file upload',
            'method': 'POST',
            'required_fields': ['file'],
            'optional_fields': ['pro_conversion'],
            'status': 'ready'
        }), 405
    
    # Handle POST requests using ConversionService
    try:
        current_app.logger.info("=== CONVERT REQUEST STARTED ===")
        
        if 'file' not in request.files:
            current_app.logger.error("No file part in request")
            return jsonify({'error': 'No file part in the request'}), 400
        
        file = request.files['file']
        if file.filename == '':
            current_app.logger.error("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        # Get conversion type from request
        use_pro_converter = request.form.get('pro_conversion') == 'on'
        
        # Get user info
        user = None
        if current_user and current_user.is_authenticated:
            user = current_user
        
        # Use ConversionService for all business logic
        conversion_service = ConversionService()
        success, result = conversion_service.process_conversion(
            file=file,
            filename=file.filename,
            use_pro_converter=use_pro_converter,
            user=user
        )
        
        if not success:
            current_app.logger.error(f"Conversion service error: {result}")
            return jsonify({'error': result}), 400
        
        current_app.logger.info("=== CONVERT REQUEST SUCCESSFUL ===")
        return jsonify(result), 202
        
    except Exception as e:
        current_app.logger.error(f"=== CONVERT REQUEST ERROR ===")
        current_app.logger.error(f"Unexpected error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

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
        # First, try to get the conversion from the database
        conversion = Conversion.query.filter_by(job_id=job_id).first()
        
        # Fallback to Celery task result
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
                'markdown': result.get('markdown', ''),  # Keep original format for main UI
                'filename': result.get('filename', '')
            })
        else:
            return jsonify({'error': 'Task completed but no result available'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error getting task result: {e}")
        return jsonify({'error': 'Error retrieving task result'}), 500

@main.route('/result/<job_id>/text')
@login_required
def task_result_text(job_id):
    """
    Get the clean text result of a completed conversion task for Pro users.
    """
    # Access control check - must be the very first operation
    if not current_user.has_pro_access:
        abort(403)
    
    try:
        # Get the conversion record
        conversion = Conversion.query.filter_by(job_id=job_id, user_id=current_user.id).first()
        if not conversion:
            return jsonify({'error': 'Conversion not found'}), 404
        
        if conversion.status != 'completed':
            return jsonify({'error': 'Conversion not completed yet'}), 400
        
        # Get the markdown content from GCS
        storage_client = get_storage_client()
        bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
        markdown_blob = bucket.blob(f"results/{conversion.id}.md")
        
        if not markdown_blob.exists():
            return jsonify({'error': 'Result file not found'}), 404
        
        # Download markdown content
        markdown_content = markdown_blob.download_as_text()
        
        # Convert to clean text using ConversionEngine
        conversion_engine = ConversionEngine()
        
        # Create temporary file with markdown content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write(markdown_content)
            temp_file_path = temp_file.name
        
        try:
            # Convert to clean text
            clean_text = conversion_engine.convert_to_clean_text(temp_file_path)
            
            # Create response with clean text
            from io import BytesIO
            response = send_file(
                BytesIO(clean_text.encode('utf-8')),
                mimetype='text/plain',
                as_attachment=True,
                download_name=f"{conversion.original_filename.rsplit('.', 1)[0]}.txt"
            )
            
            return response
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        current_app.logger.error(f"Error getting task result text: {e}")
        return jsonify({'error': 'Error retrieving task result text'}), 500

@main.route('/result/<job_id>/json')
@login_required
def task_result_json(job_id):
    """
    Get the structured JSON result of a completed conversion task for Pro users.
    """
    # Access control check - must be the very first operation
    if not current_user.has_pro_access:
        abort(403)
    
    try:
        # Get the conversion record
        conversion = Conversion.query.filter_by(job_id=job_id, user_id=current_user.id).first()
        if not conversion:
            return jsonify({'error': 'Conversion not found'}), 404
        
        if conversion.status != 'completed':
            return jsonify({'error': 'Conversion not completed yet'}), 400
        
        # Get the markdown content from GCS
        storage_client = get_storage_client()
        bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
        markdown_blob = bucket.blob(f"results/{conversion.id}.md")
        
        if not markdown_blob.exists():
            return jsonify({'error': 'Result file not found'}), 404
        
        # Download markdown content
        markdown_content = markdown_blob.download_as_text()
        
        # Convert to structured JSON using ConversionEngine
        conversion_engine = ConversionEngine()
        
        # Create temporary file with markdown content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write(markdown_content)
            temp_file_path = temp_file.name
        
        try:
            # Convert to structured JSON
            structured_doc = conversion_engine.convert_to_structured_json(temp_file_path)
            
            # Convert to JSON string
            json_content = structured_doc.model_dump_json(indent=2)
            
            # Create response with JSON
            from io import BytesIO
            response = send_file(
                BytesIO(json_content.encode('utf-8')),
                mimetype='application/json',
                as_attachment=True,
                download_name=f"{conversion.original_filename.rsplit('.', 1)[0]}.json"
            )
            
            return response
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        current_app.logger.error(f"Error getting task result json: {e}")
        return jsonify({'error': 'Error retrieving task result json'}), 500

@main.route('/stats')
def conversion_stats():
    """Display conversion statistics."""
    try:
        # Get basic stats
        total_conversions = Conversion.query.count()
        completed_conversions = Conversion.query.filter_by(status='completed').count()
        failed_conversions = Conversion.query.filter_by(status='failed').count()
        
        # Get recent conversions
        recent_conversions = Conversion.query.order_by(Conversion.created_at.desc()).limit(10).all()
        
        # Calculate success rate
        success_rate = (completed_conversions / total_conversions * 100) if total_conversions > 0 else 0
        
        stats = {
            'total_conversions': total_conversions,
            'completed_conversions': completed_conversions,
            'failed_conversions': failed_conversions,
            'success_rate': round(success_rate, 2),
            'recent_conversions': [
                {
                    'id': conv.id,
                    'filename': conv.original_filename,
                    'status': conv.status,
                    'created_at': conv.created_at.isoformat() if conv.created_at else None,
                    'processing_time': conv.processing_time
                }
                for conv in recent_conversions
            ]
        }
        
        return jsonify(stats)
        
    except Exception as e:
        current_app.logger.error(f"Error getting conversion stats: {e}")
        return jsonify({'error': 'Error retrieving statistics'}), 500

@main.route('/history')
def conversion_history():
    """Display conversion history for the current user."""
    try:
        if not current_user or not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get user's conversion history
        conversions = Conversion.query.filter_by(user_id=current_user.id).order_by(Conversion.created_at.desc()).limit(50).all()
        
        history = [
            {
                'id': conv.id,
                'filename': conv.original_filename,
                'status': conv.status,
                'conversion_type': conv.conversion_type,
                'created_at': conv.created_at.isoformat() if conv.created_at else None,
                'completed_at': conv.completed_at.isoformat() if conv.completed_at else None,
                'processing_time': conv.processing_time,
                'markdown_length': conv.markdown_length,
                'error_message': conv.error_message
            }
            for conv in conversions
        ]
        
        return jsonify({'conversions': history})
        
    except Exception as e:
        current_app.logger.error(f"Error getting conversion history: {e}")
        return jsonify({'error': 'Error retrieving history'}), 500

# Batch upload routes (moved from uploads module)
@main.route('/batch-uploader')
@login_required
def batch_uploader():
    """Render the batch uploader interface for David's use case."""
    return render_template('batch_uploader.html')

@main.route('/batch-upload', methods=['POST'])
@login_required
def batch_upload():
    """Handle batch file upload and create conversion jobs."""
    try:
        # Check if files were uploaded
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files selected'}), 400
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        # Validate files and create batch record
        valid_files = []
        batch_id = str(uuid.uuid4())
        
        # Create batch record
        batch = Batch(
            user_id=current_user.id,
            batch_id=batch_id,
            status='queued',
            total_files=0
        )
        db.session.add(batch)
        db.session.flush()  # Get the batch ID
        
        # Process each file
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_size = len(file.read())
                file.seek(0)  # Reset file pointer
                
                # Get file extension
                file_type = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                # Create conversion job record
                conversion_job = ConversionJob(
                    batch_id=batch.id,
                    user_id=current_user.id,
                    original_filename=filename,
                    file_size=file_size,
                    file_type=file_type,
                    status='queued'
                )
                db.session.add(conversion_job)
                valid_files.append({
                    'filename': filename,
                    'size': file_size,
                    'status': 'queued'
                })
        
        if not valid_files:
            db.session.rollback()
            return jsonify({'error': 'No valid files found'}), 400
        
        # Update batch with total files count
        batch.total_files = len(valid_files)
        db.session.commit()
        
        # Dispatch Celery task for batch processing
        from app.tasks import process_batch_conversions
        process_batch_conversions.delay(batch.id)
        
        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'files': valid_files,
            'message': f'Batch job created with {len(valid_files)} files'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Batch upload error: {str(e)}')
        return jsonify({'error': 'Upload failed'}), 500

@main.route('/batch-status/<batch_id>')
@login_required
def batch_status(batch_id):
    """Get the status of a batch job."""
    try:
        batch = Batch.query.filter_by(batch_id=batch_id, user_id=current_user.id).first()
        if not batch:
            return jsonify({'error': 'Batch not found'}), 404
        
        # Get conversion jobs for this batch
        jobs = ConversionJob.query.filter_by(batch_id=batch.id).all()
        
        job_statuses = [
            {
                'id': job.id,
                'filename': job.original_filename,
                'status': job.status,
                'error_message': job.error_message,
                'processing_time': job.processing_time
            }
            for job in jobs
        ]
        
        return jsonify({
            'batch_id': batch.batch_id,
            'status': batch.status,
            'total_files': batch.total_files,
            'processed_files': batch.processed_files,
            'failed_files': batch.failed_files,
            'progress_percentage': batch.progress_percentage(),
            'created_at': batch.created_at.isoformat() if batch.created_at else None,
            'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
            'jobs': job_statuses
        })
        
    except Exception as e:
        current_app.logger.error(f'Batch status error: {str(e)}')
        return jsonify({'error': 'Error retrieving batch status'}), 500

@main.route('/batch-download/<job_id>')
@login_required
def batch_download(job_id):
    """Download the result of a completed conversion job."""
    try:
        job = ConversionJob.query.filter_by(id=job_id, user_id=current_user.id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if job.status != 'completed':
            return jsonify({'error': 'Job not completed yet'}), 400
        
        if not job.markdown_content:
            return jsonify({'error': 'No content available'}), 400
        
        # Create filename for download
        base_name = job.original_filename.rsplit('.', 1)[0]
        download_filename = f"{base_name}.md"
        
        return jsonify({
            'filename': download_filename,
            'content': job.markdown_content,
            'size': job.markdown_length
        })
        
    except Exception as e:
        current_app.logger.error(f'Batch download error: {str(e)}')
        return jsonify({'error': 'Error downloading result'}), 500

@main.route('/pricing')
def pricing():
    """Display pricing information."""
    return render_template('pricing.html')

@main.route('/user-status')
def user_status():
    """Return current user status for frontend JavaScript."""
    try:
        if current_user and current_user.is_authenticated:
            # Calculate Pro access based on subscription status and trial
            subscription_status = getattr(current_user, 'subscription_status', 'free')
            has_pro_access = subscription_status in ['pro', 'trial']
            on_trial = subscription_status == 'trial'
            
            # Set appropriate usage limits based on subscription
            if has_pro_access:
                usage_limit = 1000  # Pro users get 1000 pages per month
            else:
                usage_limit = 5  # Free users get 5 pages per day
            
            return jsonify({
                'authenticated': True,
                'user_id': current_user.id,
                'email': current_user.email,
                'is_admin': getattr(current_user, 'is_admin', False),
                'subscription_status': subscription_status,
                'has_pro_access': has_pro_access,  # ✅ Added missing field
                'on_trial': on_trial,  # ✅ Added missing field
                'monthly_usage': getattr(current_user, 'monthly_usage', 0),
                'usage_limit': usage_limit
            })
        else:
            return jsonify({
                'authenticated': False,
                'user_id': None,
                'email': None,
                'is_admin': False,
                'subscription_status': 'free',
                'has_pro_access': False,
                'on_trial': False,
                'monthly_usage': 0,
                'usage_limit': current_app.config.get('ANONYMOUS_DAILY_LIMIT', 5)
            })
    except Exception as e:
        current_app.logger.error(f"Error in user_status endpoint: {e}")
        return jsonify({'error': 'Error retrieving user status'}), 500

@main.app_errorhandler(413)
def request_entity_too_large(e):
    """Handle 413 Request Entity Too Large errors."""
    return jsonify({'error': 'File too large'}), 413

@main.route('/result/<job_id>/graph')
@login_required
def task_result_graph(job_id):
    """Get knowledge graph data for a completed conversion."""
    conversion = Conversion.query.filter_by(job_id=job_id).first()
    if not conversion:
        abort(404)
    
    if conversion.user_id != current_user.id:
        abort(403)
    
    if conversion.status != 'completed':
        abort(400, description="Conversion must be completed before graph data is available")
    
    if not conversion.structured_data:
        abort(404, description="No graph data available for this conversion")
    
    # Convert financial data to knowledge graph format for frontend compatibility
    if conversion.structured_data and 'entries' in conversion.structured_data:
        # Convert financial data to knowledge graph nodes and edges
        nodes = []
        edges = []
        
        entries = conversion.structured_data.get('entries', [])
        for i, entry in enumerate(entries):
            # Create node for each person
            nodes.append({
                "id": f"person_{i}",
                "label": entry['person'],
                "type": "PERSON"
            })
            
            # Create nodes for financial values
            nodes.append({
                "id": f"total_{i}",
                "label": f"Total: {entry['total']}",
                "type": "AMOUNT"
            })
            
            # Create edge between person and their total
            edges.append({
                "source": f"person_{i}",
                "target": f"total_{i}",
                "label": "HAS_TOTAL"
            })
        
        # Add summary node
        if 'summary' in conversion.structured_data:
            nodes.append({
                "id": "summary",
                "label": conversion.structured_data['summary'],
                "type": "SUMMARY"
            })
        
        knowledge_graph = {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "source": "financial_analysis",
                "entries_count": len(entries),
                "biggest_winner": conversion.structured_data.get('biggest_winner', 'Unknown'),
                "biggest_loser": conversion.structured_data.get('biggest_loser', 'Unknown')
            }
        }
        
        return jsonify({"knowledge_graph": knowledge_graph})
    
    # Fallback to original format
    return jsonify({"knowledge_graph": conversion.structured_data})


@main.route('/result/<job_id>/export/text')
@login_required
def export_text(job_id):
    """Export clean text as a downloadable file."""
    conversion = Conversion.query.filter_by(job_id=job_id).first()
    if not conversion:
        abort(404)
    
    if conversion.user_id != current_user.id:
        abort(403)
    
    if conversion.status != 'completed':
        abort(400, description="Conversion must be completed before export is available")
    
    # Get the clean text content
    try:
        # Get the text content from the Celery task result
        from celery.result import AsyncResult
        task_result = AsyncResult(job_id)
        
        if task_result.ready() and task_result.successful():
            # Get the markdown content from the task result
            result_data = task_result.get()
            if isinstance(result_data, dict) and 'markdown' in result_data:
                text_content = result_data['markdown']
            else:
                # Fallback: try to get from GCS if available
                try:
                    storage_client = get_storage_client()
                    bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
                    blob = bucket.blob(f"results/{job_id}/result.txt")
                    text_content = blob.download_as_text()
                except Exception as gcs_error:
                    current_app.logger.error(f"GCS fallback failed for job {job_id}: {gcs_error}")
                    abort(500, description="Text content not available")
        else:
            abort(400, description="Conversion task not completed")
        
        # Create response with file download
        response = make_response(text_content)
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename="document.txt"'
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting text for job {job_id}: {e}")
        abort(500, description="Error retrieving text content")


@main.route('/result/<job_id>/pdf')
@login_required
def get_pdf(job_id):
    """Get the original PDF file for viewing."""
    conversion = Conversion.query.filter_by(job_id=job_id).first()
    if not conversion:
        abort(404)
    
    if conversion.user_id != current_user.id:
        abort(403)
    
    if conversion.status != 'completed':
        abort(400, description="Conversion must be completed before PDF is available")
    
    try:
        # Get the original PDF from GCS
        storage_client = get_storage_client()
        bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
        
        # Use the stored GCS path if available, otherwise fall back to job_id
        if conversion.gcs_path:
            file_path = conversion.gcs_path
            current_app.logger.info(f"Using stored GCS path: {file_path}")
        else:
            file_path = f"uploads/{job_id}/{conversion.original_filename}"
            current_app.logger.info(f"Using fallback path: {file_path}")
        
        current_app.logger.info(f"Attempting to retrieve PDF from GCS: {file_path}")
        current_app.logger.info(f"Job ID: {job_id}, Filename: {conversion.original_filename}")
        
        blob = bucket.blob(file_path)
        
        # Check if the blob exists
        if not blob.exists():
            current_app.logger.error(f"PDF file not found in GCS: {file_path}")
            abort(404, description="PDF file not found in storage")
        
        # Download the PDF content
        pdf_content = blob.download_as_bytes()
        current_app.logger.info(f"Successfully retrieved PDF from GCS: {len(pdf_content)} bytes")
        
        # Create response with PDF content
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="{conversion.original_filename}"'
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving PDF for job {job_id}: {e}")
        current_app.logger.error(f"Exception type: {type(e).__name__}")
        abort(500, description="Error retrieving PDF content")


@main.route('/workspace')
@login_required
def workspace():
    """Document Intelligence Workspace."""
    return render_template('index.html')

# Team Management Routes
@main.route('/team/<int:team_id>/manage')
@login_required
def manage_team(team_id):
    """Team management page for team admins."""
    # Verify current user is an admin of the specified team
    team = Team.query.get_or_404(team_id)
    if not team.is_admin(current_user):
        abort(403)
    
    # Get team members with their user information
    members = []
    for membership in team.members.all():
        user = User.query.get(membership.user_id)
        if user:
            members.append({
                'id': user.id,
                'email': user.email,
                'role': membership.role,
                'joined_at': membership.joined_at
            })
    
    return render_template('main/manage_team.html', team=team, members=members)

@main.route('/team/<int:team_id>/invite', methods=['POST'])
@login_required
def invite_team_member(team_id):
    """Invite a user to join the team."""
    # Verify current user is an admin of the specified team
    team = Team.query.get_or_404(team_id)
    if not team.is_admin(current_user):
        abort(403)
    
    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('Email address is required', 'error')
        return redirect(url_for('main.manage_team', team_id=team_id))
    
    # Find the user by email
    user = User.query.filter_by(email=email).first()
    if not user:
        flash(f'User with email {email} not found', 'error')
        return redirect(url_for('main.manage_team', team_id=team_id))
    
    # Check if user is already a member
    if team.is_member(user):
        flash(f'{email} is already a member of this team', 'error')
        return redirect(url_for('main.manage_team', team_id=team_id))
    
    try:
        # Add user to team with default 'member' role
        team.add_member(user, role='member')
        db.session.commit()
        flash(f'{email} has been invited to join the team', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error inviting user to team: {e}')
        flash('Error inviting user to team', 'error')
    
    return redirect(url_for('main.manage_team', team_id=team_id))

@main.route('/team/<int:team_id>/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_team_member(team_id, user_id):
    """Remove a user from the team."""
    # Verify current user is an admin of the specified team
    team = Team.query.get_or_404(team_id)
    if not team.is_admin(current_user):
        abort(403)
    
    # Find the user to remove
    user = User.query.get_or_404(user_id)
    
    # Check if user is actually a member of this team
    if not team.is_member(user):
        flash('User is not a member of this team', 'error')
        return redirect(url_for('main.manage_team', team_id=team_id))
    
    # Prevent removing the team owner
    if user.id == team.owner_id:
        flash('Cannot remove the team owner', 'error')
        return redirect(url_for('main.manage_team', team_id=team_id))
    
    try:
        # Remove user from team
        team.remove_member(user)
        db.session.commit()
        flash(f'{user.email} has been removed from the team', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error removing user from team: {e}')
        flash('Error removing user from team', 'error')
    
    return redirect(url_for('main.manage_team', team_id=team_id))