from flask import Blueprint, request, jsonify, g
from app.models import User

api = Blueprint('api', __name__)

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