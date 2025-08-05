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

@api.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Basic app health
        health_status = {
            'status': 'healthy',
            'timestamp': time.time(),
            'app': {
                'name': 'mdraft-app',
                'version': '1.0.0',
                'environment': os.environ.get('FLASK_ENV', 'development')
            },
            'dependencies': {},
            'services': {}
        }
        
        # Check RAG service
        try:
            from app.services.rag_service import get_rag_service
            rag_service = get_rag_service()
            rag_metrics = rag_service.get_metrics()
            health_status['services']['rag'] = {
                'enabled': rag_metrics.get('is_enabled', False),
                'available': rag_metrics.get('is_available', False),
                'dependencies_available': rag_metrics.get('dependencies_available', False),
                'model': rag_metrics.get('model_name', 'unknown'),
                'initializations': rag_metrics.get('initializations', 0),
                'import_errors': rag_metrics.get('import_errors', 0)
            }
        except Exception as e:
            health_status['services']['rag'] = {
                'error': str(e),
                'enabled': False,
                'available': False
            }
        
        # Check database connection
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            health_status['services']['database'] = {'status': 'connected'}
        except Exception as e:
            health_status['services']['database'] = {'status': 'error', 'error': str(e)}
            health_status['status'] = 'degraded'
        
        # Check Redis/Celery
        try:
            from celery import current_app as celery_app
            celery_app.control.inspect().active()
            health_status['services']['celery'] = {'status': 'connected'}
        except Exception as e:
            health_status['services']['celery'] = {'status': 'error', 'error': str(e)}
        
        # Check environment variables
        env_vars = {
            'ENABLE_RAG': os.environ.get('ENABLE_RAG', 'not_set'),
            'OPENAI_API_KEY': 'set' if os.environ.get('OPENAI_API_KEY') else 'not_set',
            'DATABASE_URL': 'set' if os.environ.get('DATABASE_URL') else 'not_set',
            'GCS_BUCKET_NAME': os.environ.get('GCS_BUCKET_NAME', 'not_set')
        }
        health_status['environment'] = env_vars
        
        return jsonify(health_status), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': time.time()
        }), 500

def check_rag_availability():
    """Check if RAG service is available and return appropriate response"""
    if not current_app.config.get('ENABLE_RAG', False):
        return jsonify({
            'error': 'RAG service is disabled',
            'message': 'RAG features are not enabled in this environment',
            'code': 'RAG_DISABLED'
        }), 503
    
    if not current_app.config.get('RAG_DEPENDENCIES_AVAILABLE', False):
        return jsonify({
            'error': 'RAG service unavailable',
            'message': 'RAG dependencies are not installed or available',
            'code': 'RAG_DEPENDENCIES_MISSING'
        }), 503
    
    if not current_app.config.get('OPENAI_AVAILABLE', False):
        return jsonify({
            'error': 'OpenAI service unavailable',
            'message': 'OpenAI API key is not configured',
            'code': 'OPENAI_NOT_CONFIGURED'
        }), 503
    
    return None  # RAG is available

@api.route('/conversion/<job_id>/summarize', methods=['POST'])
@api_key_required
def summarize_conversion(job_id):
    """Generate a configurable executive summary for a conversion."""
    
    # Check RAG availability first
    rag_check = check_rag_availability()
    if rag_check:
        return rag_check
    
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
    """Generate summary using OpenAI API"""
    if not current_app.config.get('OPENAI_API_KEY'):
        current_app.logger.error("OpenAI API key not configured")
        return None
    
    try:
        import openai
        openai.api_key = current_app.config['OPENAI_API_KEY']
        
        # Configure summary based on length
        if length == 'sentence':
            max_tokens = 50
            prompt = f"Summarize this document in one sentence: {text_content[:2000]}"
        elif length == 'paragraph':
            max_tokens = 150
            prompt = f"Summarize this document in one paragraph: {text_content[:2000]}"
        else:  # bullets
            max_tokens = 200
            prompt = f"Summarize this document in 3-5 bullet points: {text_content[:2000]}"
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes documents clearly and concisely."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        current_app.logger.error(f"Error generating summary with OpenAI: {e}")
        return None

@api.route('/conversion/<job_id>/query', methods=['POST'])
@api_key_required
def rag_query(job_id):
    """Query the document using RAG (Retrieval-Augmented Generation)."""
    
    # Check RAG availability first
    rag_check = check_rag_availability()
    if rag_check:
        return rag_check
    
    try:
        # Validate request
        data = request.get_json()
        if not data or 'question' not in data:
            return jsonify({'error': 'Question parameter is required'}), 400
        
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
        
        # Get document text content
        document_text = get_document_text(conversion)
        if not document_text:
            return jsonify({'error': 'Document text not available'}), 400
        
        # Use RAG service to generate answer
        from app.services.rag_service import get_rag_service
        rag_service = get_rag_service()
        
        if not rag_service.is_available():
            return jsonify({
                'error': 'RAG service unavailable',
                'message': 'RAG service is not properly initialized'
            }), 503
        
        # Generate answer using RAG
        answer = rag_service.generate_rag_answer(question, document_text)
        if not answer:
            return jsonify({'error': 'Failed to generate answer'}), 500
        
        return jsonify({
            'answer': answer,
            'question': question,
            'conversion_id': conversion.id
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error in RAG query: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@api.route('/metrics', methods=['GET'])
@api_key_required
def get_metrics():
    """Get application metrics and health status."""
    try:
        from app.services.rag_service import get_rag_service
        rag_service = get_rag_service()
        
        metrics = {
            'rag_service': rag_service.get_metrics(),
            'app_config': {
                'enable_rag': current_app.config.get('ENABLE_RAG', False),
                'rag_dependencies_available': current_app.config.get('RAG_DEPENDENCIES_AVAILABLE', False),
                'openai_available': current_app.config.get('OPENAI_AVAILABLE', False)
            }
        }
        
        return jsonify(metrics), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': 'Failed to get metrics'}), 500 

@api.route('/debug/dependencies', methods=['GET'])
def debug_dependencies():
    """Diagnostic endpoint to check dependency availability in production"""
    import sys
    import os
    
    diagnostics = {
        'python_version': sys.version,
        'python_path': sys.path[:3],  # First 3 paths
        'environment': os.environ.get('FLASK_ENV', 'unknown'),
        'dependencies': {}
    }
    
    # Check each dependency individually
    dependencies_to_check = [
        'tiktoken', 'annoy', 'sentence_transformers', 
        'transformers', 'openai', 'numpy', 'torch'
    ]
    
    for dep in dependencies_to_check:
        try:
            module = __import__(dep)
            diagnostics['dependencies'][dep] = {
                'available': True,
                'version': getattr(module, '__version__', 'unknown'),
                'location': getattr(module, '__file__', 'unknown')
            }
        except ImportError as e:
            diagnostics['dependencies'][dep] = {
                'available': False,
                'error': str(e)
            }
    
    return jsonify(diagnostics)

@api.route('/debug/packages', methods=['GET'])
def debug_packages():
    """Show installed packages in production"""
    import subprocess
    import sys
    
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                              capture_output=True, text=True)
        packages = result.stdout
        
        # Look for our specific packages
        relevant_packages = []
        for line in packages.split('\n'):
            if any(pkg in line.lower() for pkg in ['tiktoken', 'annoy', 'transformers', 'sentence']):
                relevant_packages.append(line.strip())
        
        return jsonify({
            'pip_list_success': result.returncode == 0,
            'relevant_packages': relevant_packages,
            'all_packages_count': len(packages.split('\n'))
        })
    except Exception as e:
        return jsonify({'error': str(e)}) 