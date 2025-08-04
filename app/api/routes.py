from flask import request, jsonify, current_app, g, url_for, Blueprint
import os
import uuid
import time
import requests
import json
from werkzeug.utils import secure_filename
from app.models import Conversion, Batch, ConversionJob, Summary, db, User
from app.tasks import convert_file_task, extract_data_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult
from app.services.conversion_service import ConversionService
from app.decorators import api_key_required

api = Blueprint('api', __name__)

@api.route('/ping', methods=['GET'])
def ping():
    return jsonify({'pong': True})

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
        task_result = AsyncResult(conversion.job_id)
        
        if task_result.ready() and task_result.successful():
            result_data = task_result.get()
            if isinstance(result_data, dict) and 'markdown' in result_data:
                return result_data['markdown']
        
        # Fallback to GCS if available
        try:
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
    """Generate summary using OpenAI API."""
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            current_app.logger.error("OpenAI API key not configured")
            return None
        
        # Create prompt based on length type
        if length == 'sentence':
            prompt = f"Summarize the following document in one sentence:\n\n{text_content[:3000]}"
        elif length == 'paragraph':
            prompt = f"Summarize the following document in one paragraph:\n\n{text_content[:3000]}"
        else:  # bullets
            prompt = f"Summarize the following document in 3-5 bullet points:\n\n{text_content[:3000]}"
        
        headers = {
            'Authorization': f"Bearer {api_key}",
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-4',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful assistant that creates concise summaries.'},
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

@api.route('/conversion/<job_id>/query', methods=['POST'])
@api_key_required
def rag_query(job_id):
    """Query the document using RAG (Retrieval-Augmented Generation)."""
    try:
        # Validate request
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
        
        # For now, return a simple response without RAG
        # TODO: Implement full RAG functionality when dependencies are available
        answer = f"Document query feature is being implemented. Your question was: {question}"
        
        return jsonify({
            'job_id': job_id,
            'question': question,
            'answer': answer,
            'citations': [],
            'relevant_chunks': []
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error in RAG query: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@api.route('/metrics', methods=['GET'])
@api_key_required
def get_metrics():
    """Get application metrics."""
    try:
        # Basic metrics for now
        metrics = {
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '1.0.0'
        }
        
        return jsonify(metrics), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': 'Internal server error'}), 500 