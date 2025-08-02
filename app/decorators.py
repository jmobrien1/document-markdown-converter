from functools import wraps
from flask_login import current_user
from flask import abort, request, jsonify, g
from app.models import User


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


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