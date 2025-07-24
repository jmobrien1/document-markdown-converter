from flask import Blueprint, request, jsonify, g
from app.models import User
from functools import wraps

api = Blueprint('api', __name__)

def api_key_required(f):
    """Decorator to require valid API key and Pro access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow CORS preflight requests
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
            
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key is missing'}), 401
            
        user = User.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
            
        # Check if user has Pro access (either premium or on trial)
        if not user.has_pro_access:
            return jsonify({'error': 'Pro access required. Please upgrade to Pro or check your trial status.'}), 403
            
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

@api.before_request
def authenticate_api_key():
    # Allow CORS preflight requests
    if request.method == 'OPTIONS':
        return
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is missing'}), 401
    user = User.query.filter_by(api_key=api_key).first()
    if user:
        g.current_user = user
    else:
        return jsonify({'error': 'Invalid API key'}), 401 