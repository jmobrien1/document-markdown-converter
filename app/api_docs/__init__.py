from flask import Blueprint

# Create the main API documentation blueprint
api_docs = Blueprint('api_docs', __name__)

# Import routes to register them
from . import routes 