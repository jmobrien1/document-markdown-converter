from flask import Blueprint
from flask_smorest import Api, Blueprint as SmorestBlueprint
from marshmallow import Schema, fields

# Create the main API documentation blueprint
api_docs = Blueprint('api_docs', __name__)

# Create Flask-Smorest API instance
api = Api(api_docs)

# Define schemas for API documentation
class ErrorSchema(Schema):
    """Schema for error responses."""
    error = fields.String(required=True, description="Error message")
    details = fields.String(description="Additional error details")

class JobResponseSchema(Schema):
    """Schema for job submission response."""
    job_id = fields.String(required=True, description="Unique job identifier")
    status_url = fields.String(required=True, description="URL to check job status")

class JobStatusSchema(Schema):
    """Schema for job status response."""
    job_id = fields.String(required=True, description="Unique job identifier")
    state = fields.String(required=True, description="Celery task state (PENDING, SUCCESS, FAILURE)")
    conversion_status = fields.String(required=True, description="Conversion status (pending, completed, failed)")
    created_at = fields.DateTime(description="Job creation timestamp")
    completed_at = fields.DateTime(description="Job completion timestamp")
    conversion_type = fields.String(description="Conversion type (standard or pro)")
    file_name = fields.String(description="Original filename")
    file_type = fields.String(description="File type extension")
    file_size = fields.Integer(description="File size in bytes")
    markdown = fields.String(description="Markdown result (if completed)")
    error_message = fields.String(description="Error message (if failed)")

class JobResultSchema(Schema):
    """Schema for job result response."""
    job_id = fields.String(required=True, description="Unique job identifier")
    markdown = fields.String(required=True, description="Markdown content")
    file_name = fields.String(description="Original filename")
    conversion_type = fields.String(description="Conversion type (standard or pro)")
    completed_at = fields.DateTime(description="Job completion timestamp")
    processing_time = fields.Float(description="Processing time in seconds")

class HealthSchema(Schema):
    """Schema for health check response."""
    status = fields.String(required=True, description="Service status")
    service = fields.String(required=True, description="Service name")
    version = fields.String(required=True, description="API version")

# Create the API documentation blueprint
docs_blp = SmorestBlueprint('docs', __name__, description='mdraft.app API Documentation')

# Register the documentation blueprint with the API
api.register_blueprint(docs_blp) 