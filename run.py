# run.py
# This is the main entry point for the application.
# To run the app: `flask run` or `python run.py`

from app import create_app
import os

# Create the Flask app instance using the app factory pattern
# This will load the configuration based on the FLASK_CONFIG environment variable
# or default to 'development'
config_name = os.getenv('FLASK_CONFIG', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    # Get port from environment variables or default to 10000 for Render compatibility
    port = int(os.environ.get('PORT', 10000))
    # Running the app with debug mode off for production readiness
    # Use `flask run --debug` for development
    app.run(host='0.0.0.0', port=port)
