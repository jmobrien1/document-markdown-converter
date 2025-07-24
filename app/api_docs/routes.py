from flask import request, jsonify, current_app, g, url_for
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import Conversion, db
from app.tasks import convert_file_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult
from marshmallow import Schema, fields
from app.api import api_key_required

from . import docs_blp, JobResponseSchema, JobStatusSchema, JobResultSchema, HealthSchema, ErrorSchema

# Define request schemas
class FileUploadSchema(Schema):
    """Schema for file upload request."""
    file = fields.Raw(required=True, description="File to convert (multipart/form-data)")
    pro_conversion = fields.String(description="Set to 'on' for Pro conversion (default: standard)")

class JobIdSchema(Schema):
    """Schema for job ID parameter."""
    job_id = fields.String(required=True, description="Unique job identifier")

@docs_blp.route('/convert', methods=['POST'])
@api_key_required
@docs_blp.arguments(FileUploadSchema, location='form')
@docs_blp.response(202, JobResponseSchema, description="Job submitted successfully")
@docs_blp.response(400, ErrorSchema, description="Invalid request")
@docs_blp.response(401, ErrorSchema, description="API key missing or invalid")
@docs_blp.response(403, ErrorSchema, description="Pro access required")
@docs_blp.response(500, ErrorSchema, description="Server error")
@docs_blp.doc(
    summary="Convert a document to Markdown",
    description="""
    Submit a document file for conversion to Markdown format.
    
    **Authentication**: Requires valid API key in `X-API-Key` header
    **Pro Access**: Requires Pro subscription or active trial
    
    **Supported Formats**:
    - PDF files (recommended for best results)
    - Images: PNG, JPG, JPEG, GIF, BMP, TIFF, WebP
    - HTML files
    
    **Conversion Types**:
    - Standard: Basic text extraction
    - Pro: Advanced OCR with Document AI (higher quality)
    
    **Response**: Returns a job ID that can be used to check status and retrieve results.
    """,
    tags=["Conversion"]
)
def api_convert_docs(args):
    """Convert a document to Markdown (documented version)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or no selected file'}), 400

    filename = secure_filename(file.filename)
    blob_name = f"uploads/{uuid.uuid4()}_{filename}"
    bucket_name = current_app.config['GCS_BUCKET_NAME']

    use_pro_converter = request.form.get('pro_conversion') == 'on'
    user = g.current_user  # Guaranteed to exist due to decorator

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

@docs_blp.route('/status/<job_id>', methods=['GET'])
@api_key_required
@docs_blp.arguments(JobIdSchema, location='path')
@docs_blp.response(200, JobStatusSchema, description="Job status retrieved successfully")
@docs_blp.response(401, ErrorSchema, description="API key missing or invalid")
@docs_blp.response(403, ErrorSchema, description="Pro access required")
@docs_blp.response(404, ErrorSchema, description="Job not found")
@docs_blp.doc(
    summary="Check job status",
    description="""
    Check the status of a conversion job.
    
    **Authentication**: Requires valid API key in `X-API-Key` header
    **Pro Access**: Requires Pro subscription or active trial
    **User Isolation**: Users can only check status of their own jobs
    
    **Response States**:
    - `PENDING`: Job is queued or processing
    - `SUCCESS`: Job completed successfully
    - `FAILURE`: Job failed with error
    
    **Conversion Status**:
    - `pending`: Job is waiting to be processed
    - `completed`: Job finished successfully
    - `failed`: Job encountered an error
    """,
    tags=["Status"]
)
def api_status_docs(args):
    """Check job status (documented version)."""
    job_id = args['job_id']
    user = g.current_user  # Guaranteed to exist due to decorator

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

@docs_blp.route('/result/<job_id>', methods=['GET'])
@api_key_required
@docs_blp.arguments(JobIdSchema, location='path')
@docs_blp.response(200, JobResultSchema, description="Markdown result retrieved successfully")
@docs_blp.response(400, ErrorSchema, description="Job not completed")
@docs_blp.response(401, ErrorSchema, description="API key missing or invalid")
@docs_blp.response(403, ErrorSchema, description="Pro access required")
@docs_blp.response(404, ErrorSchema, description="Job not found")
@docs_blp.response(500, ErrorSchema, description="Server error")
@docs_blp.doc(
    summary="Get markdown result",
    description="""
    Retrieve the markdown result for a completed conversion job.
    
    **Authentication**: Requires valid API key in `X-API-Key` header
    **Pro Access**: Requires Pro subscription or active trial
    **User Isolation**: Users can only retrieve results of their own jobs
    **Completion Required**: Job must be successfully completed
    
    **Use Cases**:
    - Get the final markdown content after job completion
    - Download converted content for further processing
    - Integrate with content management systems
    """,
    tags=["Results"]
)
def api_result_docs(args):
    """Get markdown result (documented version)."""
    job_id = args['job_id']
    user = g.current_user  # Guaranteed to exist due to decorator

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

@docs_blp.route('/health', methods=['GET'])
@docs_blp.response(200, HealthSchema, description="API health status")
@docs_blp.doc(
    summary="Check API health",
    description="""
    Check the health status of the mdraft.app API.
    
    **No Authentication Required**: This endpoint is publicly accessible
    
    **Use Cases**:
    - Monitor API availability
    - Health checks for load balancers
    - Service status monitoring
    """,
    tags=["Health"]
)
def api_health_docs():
    """Check API health (documented version)."""
    return jsonify({
        'status': 'healthy',
        'service': 'mdraft-api',
        'version': '1.0.0'
    }) 