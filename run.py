# run.py
# This is the main entry point for the application.
# To run the app: `flask run` or `python run.py`

from app import create_app
import os

# Create the Flask app instance using the app factory pattern
# The FLASK_CONFIG env var will be read by create_app
app = create_app()
