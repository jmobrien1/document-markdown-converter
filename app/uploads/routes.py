# app/uploads/routes.py
from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from . import uploads
import os
from werkzeug.utils import secure_filename
import uuid
from .. import db
from ..models import Batch, ConversionJob
# Move the tasks import inside the function where it's used

# Allowed file extensions for batch processing
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'rtf'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@uploads.route('/batch-uploader')
@login_required
def batch_uploader():
    """Render the batch uploader interface for David's use case."""
    return render_template('batch_uploader.html')

@uploads.route('/batch-upload', methods=['POST'])
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
        
        # FIXED: Import Celery task inside the function to avoid circular imports
        from ..tasks import process_batch_conversions
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

@uploads.route('/batch-status/<batch_id>')
@login_required
def batch_status(batch_id):
    """Get the status of a batch processing job."""
    try:
        # Find batch by batch_id (UUID)
        batch = Batch.query.filter_by(batch_id=batch_id, user_id=current_user.id).first()
        
        if not batch:
            return jsonify({'error': 'Batch not found'}), 404
        
        # Get all conversion jobs for this batch
        conversion_jobs = batch.conversion_jobs.all()
        
        # Build files status list
        files_status = []
        for job in conversion_jobs:
            files_status.append({
                'filename': job.original_filename,
                'status': job.status,
                'error_message': job.error_message,
                'processing_time': job.processing_time,
                'markdown_length': job.markdown_length,
                'pages_processed': job.pages_processed
            })
        
        # Calculate overall status
        status = {
            'batch_id': batch.batch_id,
            'status': batch.status,
            'progress': batch.progress_percentage(),
            'total_files': batch.total_files,
            'processed_files': batch.processed_files,
            'failed_files': batch.failed_files,
            'created_at': batch.created_at.isoformat() if batch.created_at else None,
            'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
            'files': files_status
        }
        
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.error(f'Batch status error: {str(e)}')
        return jsonify({'error': 'Failed to get status'}), 500

@uploads.route('/batch-download/<job_id>')
@login_required
def batch_download(job_id):
    """Download the results of a completed batch job."""
    try:
        # TODO: Generate and serve batch results
        # This is placeholder logic
        return jsonify({'error': 'Download not implemented yet'}), 501
        
    except Exception as e:
        current_app.logger.error(f'Batch download error: {str(e)}')
        return jsonify({'error': 'Download failed'}), 500 