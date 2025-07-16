# app/main/routes.py
# This file contains the core routes for the application.
# The /convert route now checks for the pro conversion flag.

import os
import uuid
from google.cloud import storage
from google.api_core import exceptions as google_exceptions
from flask import (
    Blueprint, render_template, request, jsonify, url_for, current_app
)
from werkzeug.utils import secure_filename
from app.tasks import convert_file_task
from flask_login import login_required

main = Blueprint('main', __name__)

def allowed_file(filename):
    """Check if the file's extension is in the allowed set."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@main.route('/')
def index():
    """Renders the main page with the file upload form."""
    return render_template('index.html')

@main.route('/convert', methods=['POST'])
@login_required
def convert():
    """
    Handles file upload, checks for pro conversion flag, and starts the task.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or no selected file'}), 400

    filename = secure_filename(file.filename)
    blob_name = f"uploads/{uuid.uuid4()}_{filename}"
    bucket_name = current_app.config['GCS_BUCKET_NAME']

    # Check if the user requested a pro conversion
    use_pro_converter = request.form.get('pro_conversion') == 'on'
    
    # --- ADDED FOR DEBUGGING ---
    current_app.logger.info(f"'/convert' route called. Pro conversion requested: {use_pro_converter}")
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_file(file)
    except Exception as e:
        current_app.logger.error(f"GCS Upload Failed: {e}")
        return jsonify({'error': 'Could not upload file to cloud storage.'}), 500

    # Pass the pro converter flag to the Celery task
    task = convert_file_task.delay(
        bucket_name,
        blob_name,
        filename,
        use_pro_converter
    )

    return jsonify({
        'job_id': task.id,
        'status_url': url_for('main.task_status', job_id=task.id)
    }), 202

@main.route('/status/<job_id>')
@login_required
def task_status(job_id):
    """
    Endpoint for the client to poll for the status of a background task.
    """
    task = convert_file_task.AsyncResult(job_id)
    
    if task.state == 'PENDING':
        response = {'state': task.state, 'status': 'Pending...'}
    elif task.state == 'PROGRESS':
        response = {'state': task.state, 'status': task.info.get('status', 'Processing...')}
    elif task.state == 'SUCCESS':
        response = {'state': 'SUCCESS', 'result': task.info}
    else: # 'FAILURE'
        response = {
            'state': 'FAILURE',
            'status': str(task.info),
            'error': task.info.get('error', 'An unknown error occurred.')
        }
        
    return jsonify(response)

@main.app_errorhandler(413)
def request_entity_too_large(e):
    """Custom error handler for 413 Request Entity Too Large."""
    max_size_mb = current_app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify(error=f"File is too large. Maximum size is {max_size_mb:.0f}MB."), 413
