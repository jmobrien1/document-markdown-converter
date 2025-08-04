from functools import wraps
from flask_login import current_user
from flask import abort, request, jsonify, g
from app.models import User, db


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def api_key_required(f):
    """
    Hybrid authentication decorator that accepts either:
    1. X-API-Key header (for external API usage) - requires has_pro_access
    2. Session-based authentication (for frontend usage) - allows any authenticated user
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try API key authentication first
        api_key = request.headers.get('X-API-Key')
        if api_key:
            user = User.query.filter_by(api_key=api_key).first()
            if user and user.has_pro_access:
                g.current_user = user
                return f(*args, **kwargs)
            else:
                return jsonify({'error': 'Invalid or expired API key'}), 401
        
        # Fallback to session-based authentication
        if current_user.is_authenticated:
            g.current_user = current_user
            return f(*args, **kwargs)
        else:
            return jsonify({'error': 'Authentication required. Please log in or provide a valid API key.'}), 401
    
    return decorated_function 