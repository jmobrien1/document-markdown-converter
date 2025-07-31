from flask import request, jsonify, current_app, g, url_for
import os
import uuid
from werkzeug.utils import secure_filename
from app.models import Conversion, Batch, ConversionJob, db
from app.tasks import convert_file_task, extract_data_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult
from app.services.conversion_service import ConversionService

from . import api, api_key_required

@api.route('/convert', methods=['POST'])
@api_key_required
def api_convert():
    """API endpoint for file conversion using ConversionService."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Get conversion type from request
    use_pro_converter = request.form.get('pro_conversion') == 'on'
    user = g.current_user  # Guaranteed to exist due to decorator

    # Use ConversionService for all business logic
    conversion_service = ConversionService()
    success, result = conversion_service.process_conversion(
        file=file,
        filename=file.filename,
        use_pro_converter=use_pro_converter,
        user=user
    )

    if not success:
        return jsonify({'error': result}), 400

    # Return success response
    status_url = url_for('main.task_status', job_id=result['job_id'], _external=True)
    return jsonify({
        'job_id': result['job_id'],
        'status_url': status_url
    }), 202

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


@api.route('/conversion/<job_id>/extract', methods=['POST'])
@api_key_required
def api_extract_data(job_id):
    """Extract structured data from a completed conversion."""
    user = g.current_user  # Now guaranteed to exist due to decorator
    
    # Query Conversion record for this job_id and user
    conversion = Conversion.query.filter_by(job_id=job_id, user_id=user.id).first()
    if not conversion:
        return jsonify({'error': 'Conversion not found'}), 404
    
    # Verify that the current_user is the owner of the conversion
    if conversion.user_id != user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if user has Pro access
    if not user.has_pro_access:
        return jsonify({'error': 'Pro access required for data extraction'}), 403
    
    # Check if conversion is completed
    if conversion.status != 'completed':
        return jsonify({'error': 'Conversion must be completed before extraction'}), 400
    
    # Check if extraction has already been performed
    if conversion.structured_data is not None:
        return jsonify({'error': 'Data extraction already performed for this conversion'}), 400
    
    try:
        # Dispatch the extraction task
        task = extract_data_task.delay(conversion.id)
        
        return jsonify({
            'task_id': task.id,
            'job_id': job_id,
            'message': 'Data extraction started'
        }), 202
        
    except Exception as e:
        current_app.logger.error(f'Failed to start extraction for job {job_id}: {e}')
        return jsonify({
            'error': 'Failed to start data extraction',
            'job_id': job_id,
            'details': str(e)
        }), 500 