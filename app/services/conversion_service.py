# app/services/conversion_service.py
# Service layer for document conversion business logic

import os
import tempfile
import time
from datetime import datetime, timezone
from flask import current_app, jsonify, request
from werkzeug.utils import secure_filename
from google.cloud import storage
from pypdf import PdfReader

from app import db
from app.models import Conversion, User, AnonymousUsage
from app.tasks import convert_file_task


class ConversionService:
    """Service class for handling document conversion business logic."""
    
    def __init__(self):
        # Standard conversion supported formats
        self.standard_extensions = {
            'docx', 'xlsx', 'xls', 'pptx', 'pdf', 'html', 'htm', 'csv', 'json', 'xml', 'epub'
        }
        # Pro conversion supported formats (Google Document AI)
        self.pro_extensions = {
            'pdf', 'gif', 'tiff', 'tif', 'jpg', 'jpeg', 'png', 'bmp', 'webp', 'html'
        }
        self.max_file_size = current_app.config.get('MAX_FILE_SIZE', 50 * 1024 * 1024)  # 50MB default
    
    def validate_file(self, file, use_pro_converter=False):
        """Validate uploaded file for security and compatibility."""
        current_app.logger.info(f"=== VALIDATE FILE DEBUG ===")
        current_app.logger.info(f"File: {file.filename if file else 'None'}")
        current_app.logger.info(f"Use pro converter: {use_pro_converter}")
        
        if not file or file.filename == '':
            current_app.logger.error("No file selected")
            return False, "No file selected"
        
        # Check file extension
        filename = secure_filename(file.filename)
        file_extension = os.path.splitext(filename)[1].lower()
        current_app.logger.info(f"File extension: {file_extension}")
        
        # Choose appropriate extension set based on conversion type
        allowed_extensions = self.pro_extensions if use_pro_converter else self.standard_extensions
        current_app.logger.info(f"Allowed extensions: {allowed_extensions}")
        
        if not file_extension or file_extension[1:] not in allowed_extensions:
            error_msg = f"File type not supported for {'Pro' if use_pro_converter else 'Standard'} conversion. Allowed types: {', '.join(allowed_extensions)}"
            current_app.logger.error(f"File validation failed: {error_msg}")
            return False, error_msg
        
        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        current_app.logger.info(f"File size: {file_size} bytes")
        
        if file_size > self.max_file_size:
            error_msg = f"File too large. Maximum size: {self.max_file_size // (1024*1024)}MB"
            current_app.logger.error(f"File too large: {error_msg}")
            return False, error_msg
        
        current_app.logger.info("File validation passed")
        return True, filename
    
    def get_pdf_page_count(self, file_path):
        """Get accurate page count for PDF files."""
        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)
                return len(reader.pages)
        except Exception as e:
            current_app.logger.error(f"Error getting PDF page count: {e}")
            return 1  # Fallback to 1 page
    
    def safe_stream_reset(self, file_stream):
        """
        Safely reset file stream to beginning with error handling.
        
        Args:
            file_stream: File stream object (werkzeug FileStorage or similar)
        """
        try:
            if hasattr(file_stream, 'seek'):
                file_stream.seek(0)
            elif hasattr(file_stream, 'stream') and hasattr(file_stream.stream, 'seek'):
                file_stream.stream.seek(0)
        except (OSError, IOError, AttributeError) as e:
            current_app.logger.warning(f"Could not reset file stream: {e}")
    
    def upload_to_gcs(self, file, filename):
        """Upload file to Google Cloud Storage."""
        try:
            # CRITICAL: Ensure stream is at beginning before upload
            self.safe_stream_reset(file)
            
            # Get storage client with proper credentials
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if credentials_json:
                # Check if it's a file path or JSON content
                if os.path.exists(credentials_json):
                    # It's a file path
                    storage_client = storage.Client.from_service_account_json(credentials_json)
                else:
                    # It's JSON content, create temporary file
                    import tempfile
                    temp_creds = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                    temp_creds.write(credentials_json)
                    temp_creds.close()
                    storage_client = storage.Client.from_service_account_json(temp_creds.name)
                    os.unlink(temp_creds.name)  # Clean up temp file
            else:
                # Fallback to default credentials
                storage_client = storage.Client()
            
            bucket_name = os.environ.get('GCS_BUCKET_NAME')
            if not bucket_name:
                raise Exception("GCS_BUCKET_NAME not configured")
                
            bucket = storage_client.bucket(bucket_name)
            
            # Create unique blob name
            import uuid
            unique_id = str(uuid.uuid4())
            blob_name = f"uploads/{unique_id}/{filename}"
            
            # Upload file with proper content type
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            content_type = self.get_content_type(file_extension)
            
            # CRITICAL: Reset stream one more time before upload
            self.safe_stream_reset(file)
            
            # Upload the file
            blob = bucket.blob(blob_name)
            blob.upload_from_file(file, content_type=content_type)
            
            current_app.logger.info(f"File uploaded to GCS: {blob_name}")
            return bucket_name, blob_name
            
        except Exception as e:
            current_app.logger.error(f"Error uploading to GCS: {e}")
            raise Exception("Failed to upload file to cloud storage")
    
    def get_content_type(self, file_extension):
        """Get appropriate content type for file extension."""
        content_types = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'doc': 'application/msword',
            'txt': 'text/plain',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'tiff': 'image/tiff',
            'tif': 'image/tiff',
            'html': 'text/html',
            'htm': 'text/html'
        }
        return content_types.get(file_extension, 'application/octet-stream')
    
    def create_conversion_record(self, user_id, session_id, filename, file_size, file_type, use_pro_converter=False, gcs_path=None):
        """Create a new conversion record in the database."""
        try:
            conversion = Conversion(
                user_id=user_id,
                session_id=session_id,
                original_filename=filename,
                file_size=file_size,
                file_type=file_type,
                conversion_type='pro' if use_pro_converter else 'standard',
                status='pending',
                gcs_path=gcs_path
            )
            
            db.session.add(conversion)
            db.session.commit()
            
            return conversion
            
        except Exception as e:
            current_app.logger.error(f"Error creating conversion record: {e}")
            raise Exception("Failed to create conversion record")
    
    def check_user_access(self, user, use_pro_converter):
        """Check if user can perform the requested conversion."""
        if use_pro_converter:
            if not user:
                return False, "Pro conversion requires user account"
            
            # Safely check pro access with fallback for missing columns
            try:
                if not user.has_pro_access:
                    return False, "Pro access required. Please upgrade to Pro or check your trial status."
            except Exception as e:
                # If has_pro_access fails due to missing columns, assume no access
                current_app.logger.warning(f"Error checking pro access: {e}")
                return False, "Pro access check failed. Please try again or contact support."
        
        return True, None
    
    def process_conversion(self, file, filename, use_pro_converter=False, user=None):
        """Main method to process a file conversion."""
        try:
            current_app.logger.info(f"=== CONVERSION SERVICE START ===")
            current_app.logger.info(f"File: {filename}, Pro: {use_pro_converter}, User: {user.id if user else 'anonymous'}")
            
            # CRITICAL: Reset stream at the very beginning
            self.safe_stream_reset(file)
            current_app.logger.info("1. File stream reset ✓")
            
            # Validate file
            current_app.logger.info("2. Starting file validation...")
            is_valid, error_message = self.validate_file(file, use_pro_converter)
            if not is_valid:
                current_app.logger.error(f"File validation failed: {error_message}")
                return False, error_message
            current_app.logger.info("2. File validation passed ✓")
            
            # CRITICAL: Reset stream after validation
            self.safe_stream_reset(file)
            
            # Check user access
            current_app.logger.info("3. Checking user access...")
            can_convert, access_error = self.check_user_access(user, use_pro_converter)
            if not can_convert:
                current_app.logger.error(f"User access check failed: {access_error}")
                return False, access_error
            current_app.logger.info("3. User access check passed ✓")
            
            # Get file size
            current_app.logger.info("4. Getting file size...")
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            current_app.logger.info(f"4. File size: {file_size} bytes ✓")
            
            # CRITICAL: Reset stream after size check
            self.safe_stream_reset(file)
            
            # Get file type
            file_extension = os.path.splitext(filename)[1].lower()
            current_app.logger.info(f"5. File extension: {file_extension} ✓")
            
            # Get page count for PDFs
            page_count = None
            if file_extension == '.pdf':
                current_app.logger.info("6. Getting PDF page count...")
                # Create temporary file to get page count
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    # Handle both FileStorage and BytesIO objects
                    if hasattr(file, 'save'):
                        # It's a FileStorage object (has save method)
                        file.save(temp_file.name)
                    else:
                        # It's a BytesIO object, write content directly
                        file.seek(0)
                        temp_file.write(file.read())
                        temp_file.flush()
                    
                    page_count = self.get_pdf_page_count(temp_file.name)
                    os.unlink(temp_file.name)
                
                # CRITICAL: Reset stream after page count check
                self.safe_stream_reset(file)
                current_app.logger.info(f"6. PDF page count: {page_count} ✓")
            
            # Upload to GCS
            current_app.logger.info("7. Starting GCS upload...")
            try:
                bucket_name, blob_name = self.upload_to_gcs(file, filename)
                current_app.logger.info(f"7. GCS upload successful: {blob_name} ✓")
            except Exception as gcs_error:
                current_app.logger.error(f"GCS upload failed: {gcs_error}")
                return False, f"Failed to upload file to cloud storage: {str(gcs_error)}"
            
            # Create conversion record
            current_app.logger.info("8. Creating conversion record...")
            try:
                user_id = user.id if user else None
                session_id = request.cookies.get('session_id', 'anonymous')
                conversion = self.create_conversion_record(
                    user_id, session_id, filename, file_size, file_extension, use_pro_converter, blob_name
                )
                current_app.logger.info(f"8. Conversion record created: {conversion.id} ✓")
            except Exception as db_error:
                current_app.logger.error(f"Database record creation failed: {db_error}")
                return False, f"Failed to create conversion record: {str(db_error)}"
            
            # Get Google Cloud credentials
            current_app.logger.info("9. Checking Google Cloud credentials...")
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if not credentials_json:
                current_app.logger.error("Google Cloud credentials not configured")
                return False, "Google Cloud credentials not configured"
            current_app.logger.info("9. Google Cloud credentials found ✓")
            
            # Start conversion task
            current_app.logger.info("10. Starting Celery task...")
            try:
                task = convert_file_task.delay(
                    bucket_name,
                    blob_name,
                    filename,
                    use_pro_converter,
                    conversion.id,
                    page_count,
                    credentials_json
                )
                current_app.logger.info(f"10. Celery task queued: {task.id} ✓")
                
                # --- CRITICAL FIX: Save the Celery job_id to the database record ---
                conversion.job_id = task.id
                db.session.commit()
                current_app.logger.info(f"10.5. Job ID saved to database: {task.id} ✓")
                # --- END FIX ---
                
            except Exception as celery_error:
                current_app.logger.error(f"Celery task dispatch failed: {celery_error}")
                return False, f"Failed to queue conversion task: {str(celery_error)}"
            
            # Update anonymous usage if applicable
            if not user:
                current_app.logger.info("11. Updating anonymous usage...")
                try:
                    session_id = request.cookies.get('session_id', 'anonymous')
                    usage = AnonymousUsage.get_or_create_session(session_id, request.remote_addr)
                    usage.increment_usage()
                    current_app.logger.info("11. Anonymous usage updated ✓")
                except Exception as usage_error:
                    current_app.logger.warning(f"Anonymous usage update failed: {usage_error}")
            
            current_app.logger.info("=== CONVERSION SERVICE SUCCESS ===")
            return True, {
                'job_id': task.id,
                'conversion_id': conversion.id,
                'status': 'queued'
            }
            
        except Exception as e:
            current_app.logger.error(f"=== CONVERSION SERVICE ERROR ===")
            current_app.logger.error(f"Unexpected error: {e}")
            import traceback
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e)
    
    def get_conversion_status(self, conversion_id):
        """Get the status of a conversion."""
        try:
            conversion = Conversion.query.get(conversion_id)
            if not conversion:
                return False, "Conversion not found"
            
            return True, {
                'id': conversion.id,
                'status': conversion.status,
                'filename': conversion.original_filename,
                'created_at': conversion.created_at.isoformat() if conversion.created_at else None,
                'completed_at': conversion.completed_at.isoformat() if conversion.completed_at else None,
                'error_message': conversion.error_message
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting conversion status: {e}")
            return False, str(e)
    
    def get_conversion_result(self, conversion_id):
        """Get the result of a completed conversion."""
        try:
            conversion = Conversion.query.get(conversion_id)
            if not conversion:
                return False, "Conversion not found"
            
            if conversion.status != 'completed':
                return False, "Conversion not completed yet"
            
            return True, {
                'id': conversion.id,
                'filename': conversion.original_filename,
                'markdown_length': conversion.markdown_length,
                'processing_time': conversion.processing_time,
                'pages_processed': getattr(conversion, 'pages_processed', None)
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting conversion result: {e}")
            return False, str(e) 