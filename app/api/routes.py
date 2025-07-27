from flask import request, jsonify, current_app, g, url_for
import os
import uuid
from werkzeug.utils import secure_filename
from app.models import Conversion, Batch, ConversionJob, db
from app.tasks import convert_file_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult

from . import api, api_key_required

@api.route('/convert', methods=['POST'])
@api_key_required
def api_convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or no selected file'}), 400

    filename = secure_filename(file.filename)
    blob_name = f"uploads/{uuid.uuid4()}_{filename}"
    bucket_name = current_app.config['GCS_BUCKET_NAME']

    use_pro_converter = request.form.get('pro_conversion') == 'on'
    user = g.current_user  # Now guaranteed to exist due to decorator

    try:
        storage_client = get_storage_client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_file(file)
    except Exception as e:
        current_app.logger.error(f"GCS Upload Failed: {e}")
        return jsonify({'error': 'Could not upload file to cloud storage.'}), 500

    # Get file size
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    try:
        conversion = Conversion(
            user_id=user.id,
            session_id=None,
            original_filename=filename,
            file_size=file_size,
            file_type=os.path.splitext(filename)[1].lower(),
            conversion_type='pro' if use_pro_converter else 'standard',
            status='pending'
        )
        db.session.add(conversion)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database error occurred. Please try again.'}), 500

    # Start the conversion task
    task = convert_file_task.delay(
        bucket_name,
        blob_name,
        filename,
        use_pro_converter,
        conversion.id
    )

    try:
        conversion.job_id = task.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to store job_id: {e}")

    status_url = url_for('main.task_status', job_id=task.id, _external=True)
    return jsonify({'job_id': task.id, 'status_url': status_url}), 202 

@api.route('/status/<job_id>', methods=['GET'])
@api_key_required
def api_status(job_id):
    user = g.current_user  # Now guaranteed to exist due to decorator

    # Query Celery for task status
    task = AsyncResult(job_id)

    # Query Conversion record for this job_id and user
    conversion = Conversion.query.filter_by(job_id=job_id, user_id=user.id).first()
    if not conversion:
        return jsonify({'error': 'Conversion not found'}), 404

    response = {
        'job_id': job_id,
        'state': task.state,
        'conversion_status': conversion.status,
        'created_at': conversion.created_at.isoformat() if conversion.created_at else None,
        'completed_at': conversion.completed_at.isoformat() if conversion.completed_at else None,
        'conversion_type': conversion.conversion_type,
        'file_name': conversion.original_filename,
        'file_type': conversion.file_type,
        'file_size': conversion.file_size,
    }

    if task.state == 'SUCCESS' and conversion.status == 'completed':
        # Fetch markdown result from GCS
        try:
            storage_client = get_storage_client()
            bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
            output_blob = bucket.blob(f"results/{conversion.id}.md")
            markdown = output_blob.download_as_text()
            response['markdown'] = markdown
        except Exception as e:
            response['markdown_error'] = f'Could not fetch markdown: {str(e)}'
    elif task.state == 'FAILURE':
        response['error_message'] = conversion.error_message

    return jsonify(response)

@api.route('/result/<job_id>', methods=['GET'])
@api_key_required
def api_result(job_id):
    """Get the markdown result for a completed conversion job."""
    user = g.current_user  # Now guaranteed to exist due to decorator

    # Query Conversion record for this job_id and user
    conversion = Conversion.query.filter_by(job_id=job_id, user_id=user.id).first()
    if not conversion:
        return jsonify({'error': 'Conversion not found'}), 404

    # Query Celery for task status
    task = AsyncResult(job_id)

    # Check if the job is successful
    if task.state != 'SUCCESS' or conversion.status != 'completed':
        return jsonify({
            'error': 'Job not completed',
            'job_id': job_id,
            'state': task.state,
            'conversion_status': conversion.status
        }), 400

    # Fetch markdown result from GCS
    try:
        storage_client = get_storage_client()
        bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
        output_blob = bucket.blob(f"results/{conversion.id}.md")
        markdown = output_blob.download_as_text()
        
        return jsonify({
            'job_id': job_id,
            'markdown': markdown,
            'file_name': conversion.original_filename,
            'conversion_type': conversion.conversion_type,
            'completed_at': conversion.completed_at.isoformat() if conversion.completed_at else None,
            'processing_time': conversion.processing_time
        })
    except Exception as e:
        current_app.logger.error(f"Failed to fetch markdown for job {job_id}: {e}")
        return jsonify({
            'error': 'Could not fetch markdown result',
            'job_id': job_id,
            'details': str(e)
        }), 500

@api.route('/health', methods=['GET'])
def api_health():
    """Health check endpoint for the API."""
    return jsonify({
        'status': 'healthy',
        'service': 'mdraft-api',
        'version': '1.0.0'
    })


@api.route('/batch/<batch_id>/status', methods=['GET'])
@api_key_required
def api_batch_status(batch_id):
    """Get the status of a batch processing job."""
    user = g.current_user  # Now guaranteed to exist due to decorator
    
    try:
        # Find batch by batch_id (UUID)
        batch = Batch.query.filter_by(batch_id=batch_id, user_id=user.id).first()
        
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
                'pages_processed': job.pages_processed,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None
            })
        
        # Calculate overall status
        response = {
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
        
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f'Batch status API error: {str(e)}')
        return jsonify({'error': 'Failed to get batch status'}), 500 