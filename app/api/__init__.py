# Lazy import to avoid circular dependencies
def get_api_blueprint():
    from .routes import api
    return api

# Re-export for backward compatibility
from app.decorators import api_key_required

# Import the api blueprint for direct access
try:
    from .routes import api
except ImportError:
    # If routes.py fails to import, create a placeholder
    from flask import Blueprint
    api = Blueprint('api', __name__)
    
    @api.route('/error', methods=['GET'])
    def api_error():
        return {'error': 'API routes failed to load'}, 500

__all__ = ['get_api_blueprint', 'api_key_required', 'api'] 