from flask import request, jsonify, current_app, g, url_for
import os
import uuid
from werkzeug.utils import secure_filename
from app.models import Conversion, db
from app.tasks import convert_file_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult

from . import api

@api.route('/convert', methods=['POST'])
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
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'API user not found'}), 401

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
def api_status(job_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'API user not found'}), 401

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