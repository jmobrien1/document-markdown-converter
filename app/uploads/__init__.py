# app/uploads/__init__.py
from flask import Blueprint

uploads = Blueprint('uploads', __name__)

from . import routes 