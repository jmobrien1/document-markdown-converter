from flask import jsonify, current_app
from datetime import datetime, timezone
from . import health
from sqlalchemy import text

# --- /health ---
@health.route('/health')
def health_check():
    """General health check endpoint for monitoring service status, including GCS."""
    dependencies = {}
    status = 'healthy'

    # Test database connection
    try:
        from app.models import User
        User.query.first()
        dependencies['database'] = 'healthy'
    except Exception as e:
        dependencies['database'] = f'unhealthy: {str(e)}'
        status = 'degraded'

    # Test Redis/Celery connection
    try:
        from app import celery
        celery.control.ping(timeout=1.0)
        dependencies['celery'] = 'healthy'
    except Exception as e:
        dependencies['celery'] = f'unhealthy: {str(e)}'
        status = 'degraded'

    # Test Google Cloud Storage connection
    try:
        from app.utils import get_storage_client
        client = get_storage_client()
        bucket_name = current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.get_bucket(bucket_name)
        blobs = list(bucket.list_blobs(max_results=1))
        dependencies['gcs'] = 'healthy' if blobs is not None else 'empty-bucket'
    except Exception as e:
        dependencies['gcs'] = f'unhealthy: {str(e)}'
        status = 'degraded'

    health_data = {
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dependencies': dependencies
    }
    status_code = 200 if status == 'healthy' else 503
    return jsonify(health_data), status_code

# --- /health/web ---
@health.route('/health/web')
def health_web():
    """Web service health check endpoint."""
    dependencies = {}
    status = 'healthy'
    try:
        from app.models import User
        User.query.first()
        dependencies['database'] = 'healthy'
    except Exception as e:
        dependencies['database'] = f'unhealthy: {str(e)}'
        status = 'degraded'
    try:
        import stripe
        dependencies['stripe'] = 'available'
    except ImportError:
        dependencies['stripe'] = 'not_available'
        status = 'degraded'
    try:
        from app import celery
        celery.control.ping(timeout=1.0)
        dependencies['celery'] = 'healthy'
    except Exception as e:
        dependencies['celery'] = f'unhealthy: {str(e)}'
    health_data = {
        'service': 'web',
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dependencies': dependencies
    }
    status_code = 200 if status == 'healthy' else 503
    return jsonify(health_data), status_code

# --- /health/worker ---
@health.route('/health/worker')
def health_worker():
    """Worker service health check endpoint."""
    dependencies = {}
    status = 'healthy'
    try:
        from app.tasks import convert_file_task
        dependencies['tasks'] = 'available'
    except Exception as e:
        dependencies['tasks'] = f'unavailable: {str(e)}'
        status = 'unhealthy'
    try:
        from app import celery
        inspect = celery.control.inspect()
        stats = inspect.stats()
        active_workers = len(stats) if stats else 0
        dependencies['active_workers'] = active_workers
        if active_workers == 0:
            status = 'no_workers'
    except Exception as e:
        dependencies['celery_inspect'] = f'failed: {str(e)}'
        status = 'unhealthy'
    try:
        import stripe
        dependencies['stripe'] = 'available_but_not_needed'
    except ImportError:
        dependencies['stripe'] = 'not_available_as_expected'
    health_data = {
        'service': 'worker',
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dependencies': dependencies
    }
    status_code = 200 if status in ['healthy', 'no_workers'] else 503
    return jsonify(health_data), status_code 