from flask import request, jsonify, current_app, g, url_for, Blueprint
import os
import uuid
from werkzeug.utils import secure_filename
from app.models import Conversion, Batch, ConversionJob, Summary, db, User, RAGChunk, RAGQuery # Added RAGChunk, RAGQuery
from app.tasks import convert_file_task, extract_data_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult
from app.services.conversion_service import ConversionService
# RAG service will be imported only when needed to avoid startup imports
from app.decorators import api_key_required
import time

api = Blueprint('api', __name__)

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
def health_check():
    """Health check endpoint with RAG service status"""
    try:
        # Check basic application health
        health_status = {
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '1.0.0',
            'services': {
                'database': 'healthy',
                'celery': 'healthy',
                'rag_service': 'unknown'
            }
        }
        
        # Check database connectivity
        try:
            db.session.execute('SELECT 1')
            health_status['services']['database'] = 'healthy'
        except Exception as e:
            health_status['services']['database'] = 'unhealthy'
            health_status['status'] = 'degraded'
        
        # Check RAG service status
        try:
            from app.services.rag_service import get_rag_service
            rag_service = get_rag_service()
            if rag_service:
                rag_available = rag_service.is_available()
                health_status['services']['rag_service'] = 'healthy' if rag_available else 'unavailable'
                if not rag_available:
                    health_status['status'] = 'degraded'
            else:
                health_status['services']['rag_service'] = 'disabled'
        except Exception as e:
            health_status['services']['rag_service'] = 'error'
            health_status['status'] = 'degraded'
        
        # Check Celery (if configured)
        try:
            from celery import current_app as celery_app
            celery_app.control.inspect().active()
            health_status['services']['celery'] = 'healthy'
        except Exception as e:
            health_status['services']['celery'] = 'unavailable'
            health_status['status'] = 'degraded'
        
        return jsonify(health_status), 200 if health_status['status'] == 'healthy' else 503
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }), 500


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

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from app.models import Conversion, Summary
from app import db
import os
import requests
import json

api = Blueprint('api', __name__, url_prefix='/api/v1')

def require_api_key(f):
    """Decorator to require API key authentication."""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # For now, we'll use a simple API key check
        # In production, this should be a proper API key validation
        expected_key = os.getenv('API_KEY', 'test-api-key')
        if api_key != expected_key:
            return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@api.route('/conversion/<job_id>/summarize', methods=['POST'])
@api_key_required
def summarize_conversion(job_id):
    """Generate a configurable executive summary for a conversion."""
    try:
        # Validate request
        data = request.get_json()
        if not data or 'length' not in data:
            return jsonify({'error': 'Length parameter is required'}), 400
        
        length = data['length']
        if length not in ['sentence', 'paragraph', 'bullets']:
            return jsonify({'error': 'Length must be one of: sentence, paragraph, bullets'}), 400
        
        # Get conversion and verify ownership
        conversion = Conversion.query.filter_by(job_id=job_id).first()
        if not conversion:
            return jsonify({'error': 'Conversion not found'}), 404
        
        # Check if user owns this conversion
        user = g.current_user
        if conversion.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if conversion.status != 'completed':
            return jsonify({'error': 'Conversion must be completed before summarization'}), 400
        
        # Get document text content
        document_text = get_document_text(conversion)
        if not document_text:
            return jsonify({'error': 'Document text not available'}), 400
        
        # Generate summary using LLM
        summary_content = generate_summary(document_text, length)
        if not summary_content:
            return jsonify({'error': 'Failed to generate summary'}), 500
        
        # Save summary to database
        summary = Summary(
            conversion_id=conversion.id,
            length_type=length,
            content=summary_content
        )
        db.session.add(summary)
        db.session.commit()
        
        return jsonify({
            'summary': summary_content,
            'length': length,
            'summary_id': summary.id
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error generating summary: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def get_document_text(conversion):
    """Retrieve the document text content for summarization."""
    try:
        # Try to get from Celery task result first
        from celery.result import AsyncResult
        task_result = AsyncResult(conversion.job_id)
        
        if task_result.ready() and task_result.successful():
            result_data = task_result.get()
            if isinstance(result_data, dict) and 'markdown' in result_data:
                return result_data['markdown']
        
        # Fallback to GCS if available
        try:
            from app.main.routes import get_storage_client
            storage_client = get_storage_client()
            bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
            blob = bucket.blob(f"results/{conversion.job_id}/result.txt")
            return blob.download_as_text()
        except Exception as gcs_error:
            current_app.logger.error(f"GCS fallback failed: {gcs_error}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Error retrieving document text: {e}")
        return None

def generate_summary(text_content, length):
    """Generate summary using external LLM API."""
    try:
        # Use OpenAI API (you can replace with other LLM providers)
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            current_app.logger.error("OpenAI API key not configured")
            return None
        
        # Construct prompt based on length
        if length == 'sentence':
            prompt = f"Summarize the following document in exactly one sentence:\n\n{text_content[:4000]}"
        elif length == 'paragraph':
            prompt = f"Summarize the following document in a well-structured paragraph of 4-6 sentences:\n\n{text_content[:4000]}"
        elif length == 'bullets':
            prompt = f"Summarize the following document as 3-5 distinct bullet points:\n\n{text_content[:4000]}"
        
        # Make API call to OpenAI
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-4',
            'messages': [
                {'role': 'system', 'content': 'You are a professional document summarizer. Provide clear, accurate summaries.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 500,
            'temperature': 0.3
        }
        
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            current_app.logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Error calling LLM API: {e}")
        return None 

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from app.models import Conversion, Summary
from app import db
import os
import requests
import json

api = Blueprint('api', __name__, url_prefix='/api/v1')

def require_api_key(f):
    """Decorator to require API key authentication."""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # For now, we'll use a simple API key check
        # In production, this should be a proper API key validation
        expected_key = os.getenv('API_KEY', 'test-api-key')
        if api_key != expected_key:
            return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@api.route('/conversion/<job_id>/query', methods=['POST'])
@api_key_required
def rag_query(job_id):
    """Perform a RAG (Retrieval-Augmented Generation) query on a completed conversion."""
    try:
        data = request.get_json()
        if not data or 'question' not in data:
            return jsonify({'error': 'Question is required'}), 400

        question = data['question']

        # Get conversion and verify ownership
        conversion = Conversion.query.filter_by(job_id=job_id).first()
        if not conversion:
            return jsonify({'error': 'Conversion not found'}), 404

        # Check if user owns this conversion
        user = g.current_user
        if conversion.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        if conversion.status != 'completed':
            return jsonify({'error': 'Conversion must be completed before querying'}), 400

        # Import RAG service only when needed
        from app.services.rag_service import get_rag_service
        rag_service = get_rag_service()
        
        # Check if RAG service is available
        if not rag_service or not rag_service.is_available():
            return jsonify({'error': 'RAG service is not available. Please try again later.'}), 503

        # Get document text for processing
        document_text = conversion.extracted_text
        if not document_text:
            return jsonify({'error': 'No document text available for querying'}), 400

        # Process document through RAG pipeline
        chunks = rag_service.chunk_text(document_text)
        if not chunks:
            return jsonify({'error': 'Failed to process document text'}), 500

        # Store chunks in database
        if not rag_service.store_document_chunks(conversion.id, chunks):
            return jsonify({'error': 'Failed to store document chunks'}), 500

        # Search for relevant chunks
        relevant_chunks = rag_service.search_similar_chunks(question, top_k=5)
        if not relevant_chunks:
            return jsonify({'error': 'No relevant information found in document'}), 404

        # Generate answer using LLM (simplified for now)
        answer = f"Based on the document, here's what I found: {relevant_chunks[0]['chunk_text'][:200]}..."

        # Format citations
        citations = []
        for chunk in relevant_chunks:
            citations.append({
                'chunk_id': chunk['chunk_id'],
                'text': chunk['chunk_text'][:150] + '...',
                'score': chunk['similarity_score']
            })

        # Save query for analytics
        rag_service.save_query(question, relevant_chunks, user.id)

        return jsonify({
            'job_id': job_id,
            'question': question,
            'answer': answer,
            'citations': citations,
            'relevant_chunks': relevant_chunks
        }), 200

    except Exception as e:
        current_app.logger.error(f"RAG query API error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def get_document_text(conversion):
    """Retrieve the document text content for RAG query."""
    try:
        # Try to get from Celery task result first
        from celery.result import AsyncResult
        task_result = AsyncResult(conversion.job_id)
        
        if task_result.ready() and task_result.successful():
            result_data = task_result.get()
            if isinstance(result_data, dict) and 'markdown' in result_data:
                return result_data['markdown']
        
        # Fallback to GCS if available
        try:
            from app.main.routes import get_storage_client
            storage_client = get_storage_client()
            bucket = storage_client.bucket(current_app.config['GCS_BUCKET_NAME'])
            blob = bucket.blob(f"results/{conversion.job_id}/result.txt")
            return blob.download_as_text()
        except Exception as gcs_error:
            current_app.logger.error(f"GCS fallback failed for RAG query: {gcs_error}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Error retrieving document text for RAG query: {e}")
        return None 

@api.route('/metrics', methods=['GET'])
@api_key_required
def get_metrics():
    """Get application metrics including RAG service metrics"""
    try:
        from app.services.rag_service import get_rag_service
        rag_service = get_rag_service()
        
        if rag_service:
            rag_metrics = rag_service.get_metrics()
        else:
            rag_metrics = {
                'is_available': False,
                'is_enabled': False,
                'error': 'RAG service disabled'
            }
            
        metrics = {
            'timestamp': time.time(),
            'rag_service': rag_metrics,
            'database': {
                'connections': 'healthy'  # Simplified for now
            }
        }
        
        return jsonify(metrics), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': 'Failed to get metrics'}), 500 