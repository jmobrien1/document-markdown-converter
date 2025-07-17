# utils.py
# Core utilities for file handling, conversion logic, and job tracking

import os
import uuid
import subprocess
import threading
import time
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app, session
# Google Cloud libraries will now find credentials automatically via the environment variable
from google.cloud import storage, documentai_v1 as documentai
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

# Simplified: No longer need the _get_gcp_credentials helper function

def upload_file(file_to_upload, bucket_name, object_name):
    """Uploads a file to the bucket. Credentials are found automatically."""
    try:
        # Initialize client without arguments. It will use GOOGLE_APPLICATION_CREDENTIALS.
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        file_to_upload.seek(0)
        blob.upload_from_file(file_to_upload)
        
        current_app.logger.info(f"File {object_name} uploaded to {bucket_name}.")
        return True
    except Exception as e:
        # The exception will now be more specific if there's a problem
        current_app.logger.error(f"GCS Upload Failed: {e}")
        return False

def allowed_file(filename):
    """Check if file extension is allowed."""
    if not filename or '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_EXTENSIONS']

def convert_with_docai(file_path, timeout=120):
    """Convert file using Google Document AI (Pro conversion)."""
    try:
        current_app.logger.info(f"Starting Document AI conversion: {file_path}")
        
        # Initialize client without arguments.
        client_options = {"api_endpoint": f"{current_app.config['DOCAI_LOCATION']}-documentai.googleapis.com"}
        client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        file_ext = os.path.splitext(file_path)[1].lower()
        mime_type_map = {'.pdf': 'application/pdf', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.doc': 'application/msword'}
        mime_type = mime_type_map.get(file_ext, 'application/pdf')
        
        # The project_id will be discovered from the credentials file automatically
        name = client.processor_path(
            current_app.config['GOOGLE_CLOUD_PROJECT'], 
            current_app.config['DOCAI_LOCATION'], 
            current_app.config['DOCAI_PROCESSOR_ID']
        )
        
        raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        
        result = client.process_document(request=request)
        markdown_content = result.document.text
        
        current_app.logger.info(f"Document AI conversion successful, {len(markdown_content)} characters")
        return markdown_content, None
        
    except Exception as e:
        error_msg = f"Document AI conversion failed: {str(e)}"
        current_app.logger.error(error_msg)
        return None, error_msg

# --- All other functions from your file remain below, unchanged ---

def get_file_size_mb(file_path):
    """Get file size in MB."""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)

def check_conversion_limits(user_id=None, session_id=None):
    """Check if user/session can perform conversions."""
    from flask_login import current_user
    
    if current_user.is_authenticated:
        return True, None
    
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
        result = subprocess.run(['markitdown', file_path], capture_output=True, text=True, timeout=timeout, check=True)
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

def perform_conversion(job_id, file_path, original_filename, use_pro=False, user_id=None, session_id=None):
    """Perform the actual file conversion in a background thread."""
    job = conversion_jobs.get(job_id)
    if not job:
        current_app.logger.error(f"Job {job_id} not found")
        return
    
    start_time = time.time()
    
    try:
        job.update_status('processing', progress=10)
        current_app.logger.info(f"Starting conversion job {job_id}: {original_filename}")
        
        conversion = Conversion(user_id=user_id, session_id=session_id, original_filename=original_filename, file_size=os.path.getsize(file_path), file_type=os.path.splitext(original_filename)[1].lower(), conversion_type='pro' if use_pro else 'standard', status='processing')
        db.session.add(conversion)
        db.session.commit()
        
        job.update_status('processing', progress=30)
        
        timeout = current_app.config.get('CONVERSION_TIMEOUT', 120)
        
        if use_pro:
            markdown_content, error = convert_with_docai(file_path, timeout)
        else:
            markdown_content, error = convert_with_markitdown(file_path, timeout)
        
        job.update_status('processing', progress=80)
        
        if error:
            job.update_status('failed', error=error)
            conversion.status = 'failed'
            conversion.error_message = error
            conversion.completed_at = datetime.utcnow()
            conversion.processing_time = time.time() - start_time
            db.session.commit()
            current_app.logger.error(f"Conversion failed for job {job_id}: {error}")
            return
        
        job.update_status('completed', progress=100, result={'markdown': markdown_content, 'filename': original_filename, 'length': len(markdown_content), 'conversion_type': 'pro' if use_pro else 'standard'})
        
        conversion.status = 'completed'
        conversion.completed_at = datetime.utcnow()
        conversion.processing_time = time.time() - start_time
        conversion.markdown_length = len(markdown_content)
        db.session.commit()
        
        if not user_id and session_id:
            usage = AnonymousUsage.get_or_create_session(session_id)
            usage.increment_usage()
        
        current_app.logger.info(f"Conversion completed for job {job_id}: {len(markdown_content)} characters")
        
    except Exception as e:
        error_msg = f"Unexpected error in conversion: {str(e)}"
        job.update_status('failed', error=error_msg)
        
        if 'conversion' in locals():
            conversion.status = 'failed'
            conversion.error_message = error_msg
            conversion.completed_at = datetime.utcnow()
            conversion.processing_time = time.time() - start_time
            db.session.commit()
        
        current_app.logger.error(f"Unexpected error in job {job_id}: {str(e)}")
    
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                current_app.logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            current_app.logger.error(f"Failed to clean up file {file_path}: {str(e)}")

def start_conversion_job(file, use_pro=False, user_id=None, session_id=None):
    """Start a new conversion job."""
    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    if not filename:
        filename = f"upload_{int(time.time())}"
    
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
    file.seek(0)
    file.save(file_path)
    
    job = ConversionJob(job_id, filename, use_pro)
    conversion_jobs[job_id] = job
    
    thread = threading.Thread(target=perform_conversion, args=(job_id, file_path, filename, use_pro, user_id, session_id))
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
    to_remove = [job_id for job_id, job in conversion_jobs.items() if job.created_at.timestamp() < cutoff_time]
    for job_id in to_remove:
        del conversion_jobs[job_id]
    if to_remove:
        current_app.logger.info(f"Cleaned up {len(to_remove)} old conversion jobs")

def start_celery_conversion_job(file, use_pro=False, user_id=None):
    """Placeholder for Celery-based async conversion."""
    return start_conversion_job(file, use_pro, user_id)
