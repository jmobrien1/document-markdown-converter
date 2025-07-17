# utils.py
# Core utilities for file handling, conversion logic, and job tracking

import os
import uuid
import subprocess
import threading
import time
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app, session
from google.oauth2 import service_account
from google.cloud import documentai_v1 as documentai
from models import Conversion, AnonymousUsage, User
from app import db

# In-memory job tracking for conversion status
conversion_jobs = {}

class ConversionJob:
    """Class to track conversion job status."""
    
    def __init__(self, job_id, filename, use_pro=False):
        self.job_id = job_id
        self.filename = filename
        self.use_pro = use_pro
        self.status = 'pending'
        self.progress = 0
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.completed_at = None
    
    def update_status(self, status, progress=None, result=None, error=None):
        """Update job status."""
        self.status = status
        if progress is not None:
            self.progress = progress
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error
        if status in ['completed', 'failed']:
            self.completed_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert job to dictionary for JSON response."""
        return {
            'job_id': self.job_id,
            'filename': self.filename,
            'status': self.status,
            'progress': self.progress,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


def allowed_file(filename):
    """Check if file extension is allowed."""
    if not filename or '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_EXTENSIONS']


def get_file_size_mb(file_path):
    """Get file size in MB."""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)


def check_conversion_limits(user_id=None, session_id=None):
    """Check if user/session can perform conversions."""
    from flask_login import current_user
    
    if current_user.is_authenticated:
        # Logged-in users have unlimited conversions
        return True, None
    
    # Check anonymous user limits
    if not session_id:
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
    
    usage = AnonymousUsage.get_or_create_session(session_id)
    daily_limit = current_app.config['ANONYMOUS_DAILY_LIMIT']
    
    if not usage.can_convert(daily_limit):
        return False, f"Daily limit reached. Anonymous users can convert {daily_limit} files per day. Please sign up for unlimited conversions."
    
    return True, None


def convert_with_markitdown(file_path, timeout=120):
    """Convert file using markitdown CLI tool."""
    try:
        current_app.logger.info(f"Starting markitdown conversion: {file_path}")
        
        # Run markitdown as subprocess
        result = subprocess.run(
            ['markitdown', file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        
        markdown_content = result.stdout
        current_app.logger.info(f"Markitdown conversion successful, {len(markdown_content)} characters")
        
        return markdown_content, None
        
    except subprocess.TimeoutExpired:
        error_msg = f"Conversion timed out after {timeout} seconds"
        current_app.logger.error(error_msg)
        return None, error_msg
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Markitdown conversion failed: {e.stderr or str(e)}"
        current_app.logger.error(error_msg)
        return None, error_msg
        
    except FileNotFoundError:
        error_msg = "markitdown CLI tool not found. Please install: pip install markitdown"
        current_app.logger.error(error_msg)
        return None, error_msg
        
    except Exception as e:
        error_msg = f"Unexpected error during conversion: {str(e)}"
        current_app.logger.error(error_msg)
        return None, error_msg


def convert_with_docai(file_path, timeout=120):
    """Convert file using Google Document AI (Pro conversion)."""
    try:
        current_app.logger.info(f"Starting Document AI conversion: {file_path}")
        
        # Check for required configuration
        if not current_app.config.get('GOOGLE_CLOUD_PROJECT'):
            return None, "Google Cloud Project not configured for Pro conversion"
        if not current_app.config.get('DOCAI_PROCESSOR_ID'):
            return None, "Document AI Processor not configured"

        # *** START: NEW CREDENTIALS HANDLING ***
        # Get credentials directly from the environment variable string
        gcs_json_credentials_str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if not gcs_json_credentials_str:
            return None, "Google Cloud JSON credentials not found in environment."

        # Load the credentials from the JSON string
        credentials_info = json.loads(gcs_json_credentials_str)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        # *** END: NEW CREDENTIALS HANDLING ***

        # Initialize Document AI client with credentials
        client_options = {
            "api_endpoint": f"{current_app.config['DOCAI_LOCATION']}-documentai.googleapis.com"
        }
        client = documentai.DocumentProcessorServiceClient(credentials=credentials, client_options=client_options)
        
        # Prepare the document
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        # Determine MIME type based on file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        mime_type_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword'
        }
        mime_type = mime_type_map.get(file_ext, 'application/pdf')
        
        # Prepare the request
        name = client.processor_path(
            current_app.config['GOOGLE_CLOUD_PROJECT'],
            current_app.config['DOCAI_LOCATION'],
            current_app.config['DOCAI_PROCESSOR_ID']
        )
        
        raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        
        # Process the document
        result = client.process_document(request=request)
        
        # Extract text content
        markdown_content = result.document.text
        current_app.logger.info(f"Document AI conversion successful, {len(markdown_content)} characters")
        
        return markdown_content, None
        
    except Exception as e:
        error_msg = f"Document AI conversion failed: {str(e)}"
        current_app.logger.error(error_msg)
        return None, error_msg


def perform_conversion(job_id, file_path, original_filename, use_pro=False, user_id=None, session_id=None):
    """Perform the actual file conversion in a background thread."""
    job = conversion_jobs.get(job_id)
    if not job:
        current_app.logger.error(f"Job {job_id} not found")
        return
    
    start_time = time.time()
    
    try:
        # Update job status
        job.update_status('processing', progress=10)
        current_app.logger.info(f"Starting conversion job {job_id}: {original_filename}")
        
        # Create conversion record
        conversion = Conversion(
            user_id=user_id,
            session_id=session_id,
            original_filename=original_filename,
            file_size=os.path.getsize(file_path),
            file_type=os.path.splitext(original_filename)[1].lower(),
            conversion_type='pro' if use_pro else 'standard',
            status='processing'
        )
        db.session.add(conversion)
        db.session.commit()
        
        job.update_status('processing', progress=30)
        
        # Perform conversion
        timeout = current_app.config.get('CONVERSION_TIMEOUT', 120)
        
        if use_pro:
            markdown_content, error = convert_with_docai(file_path, timeout)
        else:
            markdown_content, error = convert_with_markitdown(file_path, timeout)
        
        job.update_status('processing', progress=80)
        
        if error:
            # Conversion failed
            job.update_status('failed', error=error)
            conversion.status = 'failed'
            conversion.error_message = error
            conversion.completed_at = datetime.utcnow()
            conversion.processing_time = time.time() - start_time
            db.session.commit()
            current_app.logger.error(f"Conversion failed for job {job_id}: {error}")
            return
        
        # Conversion successful
        job.update_status('completed', progress=100, result={
            'markdown': markdown_content,
            'filename': original_filename,
            'length': len(markdown_content),
            'conversion_type': 'pro' if use_pro else 'standard'
        })
        
        # Update conversion record
        conversion.status = 'completed'
        conversion.completed_at = datetime.utcnow()
        conversion.processing_time = time.time() - start_time
        conversion.markdown_length = len(markdown_content)
        db.session.commit()
        
        # Update usage for anonymous users
        if not user_id and session_id:
            usage = AnonymousUsage.get_or_create_session(session_id)
            usage.increment_usage()
        
        current_app.logger.info(f"Conversion completed for job {job_id}: {len(markdown_content)} characters")
        
    except Exception as e:
        error_msg = f"Unexpected error in conversion: {str(e)}"
        job.update_status('failed', error=error_msg)
        
        # Update conversion record
        if 'conversion' in locals():
            conversion.status = 'failed'
            conversion.error_message = error_msg
            conversion.completed_at = datetime.utcnow()
            conversion.processing_time = time.time() - start_time
            db.session.commit()
        
        current_app.logger.error(f"Unexpected error in job {job_id}: {str(e)}")
    
    finally:
        # Clean up uploaded file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                current_app.logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            current_app.logger.error(f"Failed to clean up file {file_path}: {str(e)}")


def start_conversion_job(file, use_pro=False, user_id=None, session_id=None):
    """Start a new conversion job."""
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Secure the filename
    filename = secure_filename(file.filename)
    if not filename:
        filename = f"upload_{int(time.time())}"
    
    # Save file to upload folder
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
    file.save(file_path)
    
    # Create job tracker
    job = ConversionJob(job_id, filename, use_pro)
    conversion_jobs[job_id] = job
    
    # Start conversion in background thread
    thread = threading.Thread(
        target=perform_conversion,
        args=(job_id, file_path, filename, use_pro, user_id, session_id)
    )
    thread.daemon = True
    thread.start()
    
    current_app.logger.info(f"Started conversion job {job_id} for {filename}")
    
    return job_id


def get_job_status(job_id):
    """Get status of a conversion job."""
    job = conversion_jobs.get(job_id)
    if not job:
        return None
    
    return job.to_dict()


def cleanup_old_jobs(max_age_hours=24):
    """Clean up old jobs from memory (call periodically)."""
    cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)
    
    to_remove = []
    for job_id, job in conversion_jobs.items():
        if job.created_at.timestamp() < cutoff_time:
            to_remove.append(job_id)
    
    for job_id in to_remove:
        del conversion_jobs[job_id]
    
    if to_remove:
        current_app.logger.info(f"Cleaned up {len(to_remove)} old conversion jobs")


# Placeholder for future Celery integration
def start_celery_conversion_job(file, use_pro=False, user_id=None):
    """
    Placeholder for Celery-based async conversion.
    
    To implement:
    1. Install Celery: pip install celery redis
    2. Create celery_app.py with Celery configuration
    3. Create @celery.task decorated function for conversion
    4. Replace threading with: task = convert_file.delay(file_path, use_pro)
    5. Use task.id for job tracking
    """
    # For now, use the threading implementation
    return start_conversion_job(file, use_pro, user_id)
