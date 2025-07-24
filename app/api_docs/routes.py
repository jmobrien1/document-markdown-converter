from flask import request, jsonify, current_app, g, url_for, render_template_string
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import Conversion, db
from app.tasks import convert_file_task
from app.main.routes import allowed_file, get_storage_client
from celery.result import AsyncResult
from app.api import api_key_required

from . import api_docs

@api_docs.route('/', methods=['GET'])
def api_docs_swagger():
    """Serve Swagger UI for API documentation."""
    swagger_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>mdraft.app API Documentation</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css" />
        <style>
            html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
            *, *:before, *:after { box-sizing: inherit; }
            body { margin:0; background: #fafafa; }
        </style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"></script>
        <script>
            window.onload = function() {
                const ui = SwaggerUIBundle({
                    url: '/api/v1/docs/openapi.json',
                    dom_id: '#swagger-ui',
                    deepLinking: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIStandalonePreset
                    ],
                    plugins: [
                        SwaggerUIBundle.plugins.DownloadUrl
                    ],
                    layout: "StandaloneLayout"
                });
            };
        </script>
    </body>
    </html>
    """
    return swagger_html

@api_docs.route('/openapi.json', methods=['GET'])
def api_docs_openapi():
    """Serve OpenAPI specification."""
    openapi_spec = {
        "openapi": "3.0.2",
        "info": {
            "title": "mdraft.app API",
            "version": "1.0.0",
            "description": "API for converting documents to Markdown format with advanced OCR capabilities",
            "contact": {
                "name": "mdraft.app Support",
                "url": "https://mdraft.app"
            }
        },
        "servers": [
            {
                "url": "https://mdraft.app/api/v1",
                "description": "Production server"
            },
            {
                "url": "http://localhost:5000/api/v1",
                "description": "Development server"
            }
        ],
        "paths": {
            "/convert": {
                "post": {
                    "summary": "Convert a document to Markdown",
                    "description": "Submit a document file for conversion to Markdown format.",
                    "tags": ["Conversion"],
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "file": {
                                            "type": "string",
                                            "format": "binary",
                                            "description": "File to convert"
                                        },
                                        "pro_conversion": {
                                            "type": "string",
                                            "description": "Set to 'on' for Pro conversion (default: standard)"
                                        }
                                    },
                                    "required": ["file"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "202": {
                            "description": "Job submitted successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "job_id": {"type": "string"},
                                            "status_url": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "400": {"description": "Invalid request"},
                        "401": {"description": "API key missing or invalid"},
                        "403": {"description": "Pro access required"},
                        "500": {"description": "Server error"}
                    }
                }
            },
            "/status/{job_id}": {
                "get": {
                    "summary": "Check job status",
                    "description": "Check the status of a conversion job.",
                    "tags": ["Status"],
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [
                        {
                            "name": "job_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Unique job identifier"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Job status retrieved successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "job_id": {"type": "string"},
                                            "state": {"type": "string"},
                                            "conversion_status": {"type": "string"},
                                            "created_at": {"type": "string", "format": "date-time"},
                                            "completed_at": {"type": "string", "format": "date-time"},
                                            "conversion_type": {"type": "string"},
                                            "file_name": {"type": "string"},
                                            "file_type": {"type": "string"},
                                            "file_size": {"type": "integer"},
                                            "markdown": {"type": "string"},
                                            "error_message": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "401": {"description": "API key missing or invalid"},
                        "403": {"description": "Pro access required"},
                        "404": {"description": "Job not found"}
                    }
                }
            },
            "/result/{job_id}": {
                "get": {
                    "summary": "Get markdown result",
                    "description": "Retrieve the markdown result for a completed conversion job.",
                    "tags": ["Results"],
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [
                        {
                            "name": "job_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Unique job identifier"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Markdown result retrieved successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "job_id": {"type": "string"},
                                            "markdown": {"type": "string"},
                                            "file_name": {"type": "string"},
                                            "conversion_type": {"type": "string"},
                                            "completed_at": {"type": "string", "format": "date-time"},
                                            "processing_time": {"type": "number"}
                                        }
                                    }
                                }
                            }
                        },
                        "400": {"description": "Job not completed"},
                        "401": {"description": "API key missing or invalid"},
                        "403": {"description": "Pro access required"},
                        "404": {"description": "Job not found"},
                        "500": {"description": "Server error"}
                    }
                }
            },
            "/health": {
                "get": {
                    "summary": "Check API health",
                    "description": "Check the health status of the mdraft.app API.",
                    "tags": ["Health"],
                    "responses": {
                        "200": {
                            "description": "API health status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "service": {"type": "string"},
                                            "version": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key for authentication"
                }
            }
        }
    }
    return jsonify(openapi_spec) 