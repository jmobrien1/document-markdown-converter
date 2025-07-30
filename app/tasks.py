# app/tasks.py
# Complete file with Document AI batch processing and fixed text extraction

import os
import time
import tempfile
import json
import uuid
import subprocess
import shutil
from google.cloud import storage, documentai
from google.oauth2 import service_account
from google.api_core import exceptions as google_exceptions
from markitdown import MarkItDown
from celery import Celery, current_task
from datetime import datetime, timezone

# Conditional imports for Flask components
try:
    from flask import current_app
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    current_app = None

# Conditional imports for database models
try:
    from app import db
    from app.models import Conversion, User, Batch, ConversionJob
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    db = None
    Conversion = None
    User = None
    Batch = None
    ConversionJob = None

# Conditional imports for email functionality
try:
    from app.email import send_conversion_complete_email
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    send_conversion_complete_email = None

# Create Celery instance - this will be properly configured by the app factory
celery = Celery('mdraft', include=['app.tasks'])

def scan_file_for_viruses(file_path):
    """
    Scan a file for viruses using ClamAV.
    
    Args:
        file_path (str): Path to the file to scan
        
    Returns:
        tuple: (is_clean, scan_result_message)
    """
    try:
        # Check if ClamAV is available
        if not shutil.which('clamscan'):
            if FLASK_AVAILABLE:
                current_app.logger.warning("ClamAV not found, skipping virus scan")
            return True, "ClamAV not available, scan skipped"
        
        # Run ClamAV scan
        result = subprocess.run(
            ['clamscan', '--no-summary', '--infected', file_path],
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Check scan results
        if result.returncode == 0:
            # File is clean
            if FLASK_AVAILABLE:
                current_app.logger.info(f"Virus scan passed for file: {file_path}")
            return True, "File scanned successfully, no threats detected"
        elif result.returncode == 1:
            # Virus detected
            if FLASK_AVAILABLE:
                current_app.logger.error(f"VIRUS DETECTED in file: {file_path}")
                current_app.logger.error(f"ClamAV output: {result.stdout}")
            return False, f"Virus detected: {result.stdout.strip()}"
        else:
            # Scan error
            if FLASK_AVAILABLE:
                current_app.logger.error(f"Virus scan error for file: {file_path}")
                current_app.logger.error(f"ClamAV error: {result.stderr}")
            return False, f"Virus scan error: {result.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        if FLASK_AVAILABLE:
            current_app.logger.error(f"Virus scan timeout for file: {file_path}")
        return False, "Virus scan timeout"
    except Exception as e:
        if FLASK_AVAILABLE:
            current_app.logger.error(f"Error during virus scan: {e}")
        return False, f"Virus scan error: {str(e)}"

def get_accurate_pdf_page_count(file_path):
    """
    Get accurate PDF page count using pypdf library.

    Args:
        file_path (str): Path to the PDF file.

    Returns:
        int: Actual number of pages in the PDF.
    """
    try:
        # Import pypdf for accurate page counting
        from pypdf import PdfReader
        
        # Use pypdf to get accurate page count
        with open(file_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            page_count = len(pdf_reader.pages)
            if FLASK_AVAILABLE:
                current_app.logger.info(f"Accurate PDF page count: {page_count} pages")
            return page_count
            
    except ImportError:
        if FLASK_AVAILABLE:
            current_app.logger.error("pypdf library not available - this should not happen in production")
        raise Exception("PDF page counting library not available. Please contact support.")
    except Exception as e:
        if FLASK_AVAILABLE:
            current_app.logger.error(f"Error getting PDF page count: {e}")
        raise Exception(f"Error reading PDF file: {str(e)}")

def process_with_docai(credentials_path, project_id, location, processor_id, file_path, mime_type):
    """
    Call the Google Document AI API for synchronous document processing.

    Args:
        credentials_path (str): Path to the service account credentials JSON file.
        project_id (str): Google Cloud project ID.
        location (str): Processor region.
        processor_id (str): Document AI processor ID.
        file_path (str): Path to the file to process.
        mime_type (str): MIME type of the file.

    Returns:
        str: Extracted text content from the document.

    Raises:
        Exception: If the Document AI API call fails.
    """
    print("--- [Celery Task] Inside process_with_docai helper function.")
    opts = {"api_endpoint": f"{location}-documentai.googleapis.com"}
    
    try:
        # Load credentials from file for synchronous processing
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        
        client = documentai.DocumentProcessorServiceClient(
            client_options=opts,
            credentials=credentials
        )
        
        with open(file_path, "rb") as image:
            image_content = image.read()

        raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
        processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}/processorVersions/pretrained-ocr-v2.0-2023-06-02"
        
        print("--- [Celery Task] Sending request to Google Document AI API...")
        
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document
        
        return document.text
        
    except Exception as e:
        print(f"--- [Celery Task] Document AI API error: {str(e)}")
        raise e

class DocumentAIProcessor:
    def __init__(self, credentials_path, project_id, location, processor_id):
        self.credentials_path = credentials_path
        self.project_id = project_id
        self.location = location
        self.processor_id = processor_id
        self.opts = {"api_endpoint": f"{location}-documentai.googleapis.com"}
        self.processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}/processorVersions/pretrained-ocr-v2.0-2023-06-02"

    def process_with_docai_batch(self, input_gcs_uri, output_gcs_uri):
        """
        Process document using Google Document AI batch processing with comprehensive error handling.
        """
        try:
            from google.cloud import documentai
            
            # Configure the batch process request with correct API structure
            gcs_document = documentai.GcsDocument(
                gcs_uri=input_gcs_uri,
                mime_type="application/pdf"
            )
            gcs_documents = documentai.GcsDocuments(
                documents=[gcs_document]
            )
            input_config = documentai.BatchDocumentsInputConfig(
                gcs_documents=gcs_documents
            )
            
            output_config = documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                    gcs_uri=output_gcs_uri
                )
            )
            
            request = documentai.BatchProcessRequest(
                name=self.processor_name,
                input_documents=input_config,
                document_output_config=output_config
            )
            
            # Execute batch processing with timeout and retry logic
            client = documentai.DocumentProcessorServiceClient()
            
            # First attempt with standard timeout
            try:
                current_app.logger.info(f"Starting batch processing for {input_gcs_uri}")
                operation = client.batch_process_documents(request=request)
                
                # Wait for operation to complete with timeout
                result = operation.result(timeout=300)  # 5 minute timeout
                current_app.logger.info(f"Batch processing completed successfully for {input_gcs_uri}")
                return True
                
            except Exception as batch_error:
                current_app.logger.error(f"Batch processing failed for {input_gcs_uri}: {batch_error}")
                
                # Enhanced error logging: Capture detailed failure information
                try:
                    # Check if this is a Google API error with operation metadata
                    if hasattr(batch_error, 'operation') and batch_error.operation:
                        operation = batch_error.operation
                        current_app.logger.error(f"Batch operation metadata: {operation}")
                        
                        # Extract individual process statuses if available
                        if hasattr(operation, 'metadata') and operation.metadata:
                            metadata = operation.metadata
                            current_app.logger.error(f"Batch operation metadata: {metadata}")
                            
                            # Look for individual process statuses
                            if hasattr(metadata, 'individual_process_statuses'):
                                for i, status in enumerate(metadata.individual_process_statuses):
                                    current_app.logger.error(f"Individual process {i} status: {status}")
                                    if hasattr(status, 'status') and status.status:
                                        current_app.logger.error(f"  - Status code: {status.status.code}")
                                        current_app.logger.error(f"  - Status message: {status.status.message}")
                                    if hasattr(status, 'input_gcs_source'):
                                        current_app.logger.error(f"  - Input GCS source: {status.input_gcs_source}")
                                    if hasattr(status, 'output_gcs_destinations'):
                                        current_app.logger.error(f"  - Output GCS destinations: {status.output_gcs_destinations}")
                            
                            # Also check for common error patterns
                            if hasattr(metadata, 'state'):
                                current_app.logger.error(f"Batch operation state: {metadata.state}")
                            if hasattr(metadata, 'state_message'):
                                current_app.logger.error(f"Batch operation state message: {metadata.state_message}")
                    
                    # Check if this is a Google API error with error details
                    if hasattr(batch_error, 'error') and batch_error.error:
                        error = batch_error.error
                        current_app.logger.error(f"Google API error details: {error}")
                        if hasattr(error, 'code'):
                            current_app.logger.error(f"  - Error code: {error.code}")
                        if hasattr(error, 'message'):
                            current_app.logger.error(f"  - Error message: {error.message}")
                        if hasattr(error, 'details'):
                            current_app.logger.error(f"  - Error details: {error.details}")
                            
                except Exception as logging_error:
                    current_app.logger.error(f"Error while extracting detailed error information: {logging_error}")
                
                # Remove flawed fallback logic - let the real error surface
                raise batch_error
                    
        except ImportError:
            raise Exception("Google Cloud Document AI library not available")
        except Exception as e:
            current_app.logger.error(f"Document AI batch processing error for {input_gcs_uri}: {e}")
            raise Exception(f"Document AI batch processing failed: {str(e)}")

@celery.task(bind=True)
def convert_file_task(self, bucket_name, blob_name, original_filename, use_pro_converter=False, conversion_id=None, page_count=None, credentials_json=None):
    """
    Convert uploaded file to Markdown using Celery background task.
    Enhanced with comprehensive security scanning, accurate page counting, and robust error handling.
    """
    start_time = time.time()
    
    try:
        # Initialize result variables
        markdown_content = None
        structured_json_content = None
        
        # Validate credentials in worker process
        if not credentials_json:
            error_msg = "No credentials provided to worker process"
            if FLASK_AVAILABLE:
                current_app.logger.error(error_msg)
            raise Exception(error_msg)
        
        if not credentials_json.strip():
            error_msg = "Empty credentials provided to worker process"
            if FLASK_AVAILABLE:
                current_app.logger.error(error_msg)
            raise Exception(error_msg)
        
        # Create temporary credentials file in worker process
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_creds:
            temp_creds.write(credentials_json)
            temp_creds.flush()
            credentials_path = temp_creds.name
        
        print(f"--- [Celery Task] Created temporary credentials file: {credentials_path}")
        
        # Set environment variable for Google Cloud libraries
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        # Download file from GCS
        print("--- [Celery Task] DEBUG: Downloading file from GCS...")
        storage_client = storage.Client.from_service_account_json(credentials_path)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(original_filename)[1])
        temp_file_path = temp_file.name
        blob.download_to_filename(temp_file_path)
        temp_file.close()
        
        print("--- [Celery Task] File downloaded from GCS successfully.")
        
        # DEBUG: Check file size
        file_size = os.path.getsize(temp_file_path)
        print(f"--- [Celery Task] DEBUG: Downloaded file size: {file_size} bytes")
        
        # SECURITY: Virus scanning before processing
        print("--- [Celery Task] Starting virus scan...")
        is_clean, scan_result = scan_file_for_viruses(temp_file_path)
        
        if not is_clean:
            # Log security event
            if FLASK_AVAILABLE:
                current_app.logger.error(f"SECURITY EVENT: Virus detected in file {original_filename}")
                current_app.logger.error(f"Scan result: {scan_result}")
            
            # Update conversion record with failure
            if conversion_id and MODELS_AVAILABLE:
                conversion = Conversion.get_conversion_safely(conversion_id)
                if conversion:
                    conversion.status = 'failed'
                    conversion.error_message = f"Security scan failed: {scan_result}"
                    conversion.completed_at = datetime.now(timezone.utc)
                    conversion.processing_time = time.time() - start_time
                    db.session.commit()
            
            # Clean up infected file
            try:
                os.unlink(temp_file_path)
                if FLASK_AVAILABLE:
                    current_app.logger.info(f"Deleted infected file: {temp_file_path}")
            except Exception as e:
                if FLASK_AVAILABLE:
                    current_app.logger.error(f"Error deleting infected file: {e}")
            
            # Return security failure
            return {
                'status': 'FAILURE',
                'error': f'Security scan failed: {scan_result}',
                'filename': original_filename
            }
        
        print("--- [Celery Task] Virus scan passed.")
        
        # Process the file
        if use_pro_converter:
            # Check user has Pro access
            if conversion_id and MODELS_AVAILABLE:
                conversion = Conversion.get_conversion_safely(conversion_id)
                if conversion and conversion.user_id:
                    user = User.get_user_safely(conversion.user_id)
                    if not user or not user.has_pro_access:
                        raise Exception("Pro access required. Please upgrade to Pro or check your trial status.")
                    
                    # Check monthly usage limit
                    current_usage = getattr(user, 'pro_pages_processed_current_month', 0)
                    
                    # Use the accurate page count passed to the task
                    if page_count is None:
                        # This should not happen in production, but handle gracefully
                        file_extension = os.path.splitext(original_filename)[1].lower()
                        pages_processed = get_accurate_pdf_page_count(temp_file_path) if file_extension == '.pdf' else 1
                    else:
                        pages_processed = page_count
                    
                    # Check if user has exceeded monthly limit
                    monthly_limit = 1000  # Default value if Flask config not available
                    if FLASK_AVAILABLE:
                        monthly_limit = current_app.config.get('PRO_PAGES_PER_MONTH', 1000)
                    if current_usage + pages_processed > monthly_limit:
                        raise Exception(f"Monthly usage limit exceeded. Current usage: {current_usage}, attempting: {pages_processed}")
            
            print("--- [Celery Task] Starting PRO conversion path (Google Document AI).")
            
            # Get Google Cloud configuration from environment
            project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
            location = os.environ.get('DOCAI_PROCESSOR_REGION', 'us')
            processor_id = os.environ.get('DOCAI_PROCESSOR_ID')
            
            if not project_id or not processor_id:
                raise Exception("Google Cloud configuration missing. Please check GOOGLE_CLOUD_PROJECT and DOCAI_PROCESSOR_ID environment variables.")
            
            print(f"--- [Celery Task] Using Google Cloud config: Project={project_id}, Location={location}, Processor={processor_id}")
            
            # Determine file type and MIME type
            file_extension = os.path.splitext(original_filename)[1].lower()
            if file_extension == '.pdf':
                mime_type = 'application/pdf'
            elif file_extension in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            elif file_extension == '.png':
                mime_type = 'image/png'
            elif file_extension == '.tiff':
                mime_type = 'image/tiff'
            elif file_extension == '.html':
                mime_type = 'text/html'
            else:
                raise Exception(f"Unsupported file type: {file_extension}")
            
            # Initialize Google Document AI client with correct regional configuration
            from google.cloud import documentai
            from google.api_core.client_options import ClientOptions
            
            # CRITICAL FIX: Configure client with explicit regional endpoint
            api_endpoint = f"{location}-documentai.googleapis.com"
            client_options = ClientOptions(api_endpoint=api_endpoint)
            
            # Load credentials and create client
            from google.auth import default
            credentials, project = default()
            client = documentai.DocumentProcessorServiceClient(
                client_options=client_options,
                credentials=credentials
            )
            
            print(f"--- [Celery Task] Document AI client initialized with endpoint: {api_endpoint}")
            
            # Determine processing path based on page count
            if page_count and page_count > 10:
                print(f"--- [Celery Task] Large document detected ({page_count} pages) - using BATCH processing")
                
                # BATCH PROCESSING PATH
                # For batch processing, use processor path WITHOUT version
                processor_path = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
                
                # Upload file to GCS for batch processing
                storage_client = storage.Client.from_service_account_json(credentials_path)
                bucket = storage_client.bucket(os.environ.get('GCS_BUCKET_NAME'))
                
                # Generate unique batch ID
                import uuid
                batch_id = str(uuid.uuid4())
                
                # Upload input file
                input_blob_name = f"batch-input/{batch_id}/{original_filename}"
                input_blob = bucket.blob(input_blob_name)
                input_blob.upload_from_filename(temp_file_path)
                input_gcs_uri = f"gs://{bucket.name}/{input_blob_name}"
                
                # Set up output location
                output_blob_name = f"batch-output/{batch_id}/"
                output_gcs_uri = f"gs://{bucket.name}/{output_blob_name}"
                
                print(f"--- [Celery Task] Batch processing setup: Input={input_gcs_uri}, Output={output_gcs_uri}")
                
                try:
                    # Construct batch request with correct structure
                    gcs_document = documentai.GcsDocument(
                        gcs_uri=input_gcs_uri,
                        mime_type=mime_type
                    )
                    gcs_documents = documentai.GcsDocuments(
                        documents=[gcs_document]
                    )
                    input_config = documentai.BatchDocumentsInputConfig(
                        gcs_documents=gcs_documents
                    )
                    
                    gcs_output_config = documentai.DocumentOutputConfig.GcsOutputConfig(
                        gcs_uri=output_gcs_uri
                    )
                    output_config = documentai.DocumentOutputConfig(
                        gcs_output_config=gcs_output_config
                    )
                    
                    request = documentai.BatchProcessRequest(
                        name=processor_path,  # WITHOUT version for batch
                        input_documents=input_config,
                        document_output_config=output_config
                    )
                    
                    print(f"--- [Celery Task] Starting batch processing with processor: {processor_path}")
                    operation = client.batch_process_documents(request=request)
                    
                    # Wait for operation to complete
                    result = operation.result(timeout=600)  # 10 minute timeout
                    print("--- [Celery Task] Batch processing completed successfully")
                    
                    # Get operation response and metadata
                    operation_response = operation.result()
                    print(f"--- [Celery Task] Operation response: {operation_response}")
                    
                    # Get output configuration from operation metadata
                    if hasattr(operation_response, 'metadata') and operation_response.metadata:
                        metadata = operation_response.metadata
                        print(f"--- [Celery Task] Operation metadata: {metadata}")
                        
                        # Get output GCS destination from metadata
                        if hasattr(metadata, 'output_config') and metadata.output_config:
                            output_config = metadata.output_config
                            if hasattr(output_config, 'gcs_output_config') and output_config.gcs_output_config:
                                gcs_output_config = output_config.gcs_output_config
                                if hasattr(gcs_output_config, 'gcs_uri'):
                                    output_gcs_uri = gcs_output_config.gcs_uri
                                    print(f"--- [Celery Task] Output GCS URI from metadata: {output_gcs_uri}")
                                else:
                                    # Fallback to our constructed URI
                                    output_gcs_uri = output_gcs_uri
                            else:
                                # Fallback to our constructed URI
                                output_gcs_uri = output_gcs_uri
                        else:
                            # Fallback to our constructed URI
                            output_gcs_uri = output_gcs_uri
                    else:
                        # Fallback to our constructed URI
                        output_gcs_uri = output_gcs_uri
                    
                    # List all output blobs in the GCS output directory
                    output_blobs = list(bucket.list_blobs(prefix=output_blob_name))
                    print(f"--- [Celery Task] Found {len(output_blobs)} output blobs")
                    
                    if not output_blobs:
                        raise Exception("No output files found from batch processing")
                    
                    # Process all output files and combine text
                    combined_text = ""
                    for i, output_blob in enumerate(output_blobs):
                        if output_blob.name.endswith('.json'):
                            print(f"--- [Celery Task] Processing output blob {i+1}/{len(output_blobs)}: {output_blob.name}")
                            
                            # Download the JSON result
                            output_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
                            output_blob.download_to_filename(output_temp_file.name)
                            
                            try:
                                # Parse the JSON result
                                import json
                                with open(output_temp_file.name, 'r') as f:
                                    output_data = json.load(f)
                                
                                # Extract text from the processed document
                                if 'document' in output_data and 'text' in output_data['document']:
                                    document_text = output_data['document']['text']
                                    combined_text += document_text + "\n"
                                    print(f"--- [Celery Task] Extracted {len(document_text)} characters from blob {i+1}")
                                else:
                                    print(f"--- [Celery Task] Warning: No text found in blob {i+1}")
                            
                            finally:
                                # Clean up temporary file
                                os.unlink(output_temp_file.name)
                    
                    # Assign the combined text to markdown_content
                    if combined_text.strip():
                        markdown_content = combined_text.strip()
                        print(f"--- [Celery Task] Successfully extracted {len(markdown_content)} characters from batch processing")
                    else:
                        raise Exception("No text content extracted from batch processing output")
                    
                    # Clean up batch files
                    try:
                        for blob_cleanup in bucket.list_blobs(prefix=f"batch-input/{batch_id}/"):
                            blob_cleanup.delete()
                        for blob_cleanup in bucket.list_blobs(prefix=f"batch-output/{batch_id}/"):
                            blob_cleanup.delete()
                        print("--- [Celery Task] Cleaned up batch files successfully")
                    except Exception as cleanup_error:
                        print(f"--- [Celery Task] Warning: Failed to clean up batch files: {cleanup_error}")
                        # Don't fail the task if cleanup fails
                    
                except Exception as batch_error:
                    if FLASK_AVAILABLE:
                        current_app.logger.error(f"Batch processing failed: {batch_error}")
                    
                    # Enhanced error logging
                    try:
                        if hasattr(batch_error, 'operation') and batch_error.operation:
                            operation = batch_error.operation
                            if FLASK_AVAILABLE:
                                current_app.logger.error(f"Batch operation metadata: {operation}")
                            
                            if hasattr(operation, 'metadata') and operation.metadata:
                                metadata = operation.metadata
                                if FLASK_AVAILABLE:
                                    current_app.logger.error(f"Batch operation metadata: {metadata}")
                                
                                if hasattr(metadata, 'individual_process_statuses'):
                                    for i, status in enumerate(metadata.individual_process_statuses):
                                        if FLASK_AVAILABLE:
                                            current_app.logger.error(f"Individual process {i} status: {status}")
                                            if hasattr(status, 'status') and status.status:
                                                current_app.logger.error(f"  - Status code: {status.status.code}")
                                                current_app.logger.error(f"  - Status message: {status.status.message}")
                                            if hasattr(status, 'input_gcs_source'):
                                                current_app.logger.error(f"  - Input GCS source: {status.input_gcs_source}")
                                            if hasattr(status, 'output_gcs_destinations'):
                                                current_app.logger.error(f"  - Output GCS destinations: {status.output_gcs_destinations}")
                                
                                if hasattr(metadata, 'state'):
                                    if FLASK_AVAILABLE:
                                        current_app.logger.error(f"Batch operation state: {metadata.state}")
                                if hasattr(metadata, 'state_message'):
                                    if FLASK_AVAILABLE:
                                        current_app.logger.error(f"Batch operation state message: {metadata.state_message}")
                        
                        if hasattr(batch_error, 'error') and batch_error.error:
                            error = batch_error.error
                            if FLASK_AVAILABLE:
                                current_app.logger.error(f"Google API error details: {error}")
                                if hasattr(error, 'code'):
                                    current_app.logger.error(f"  - Error code: {error.code}")
                                if hasattr(error, 'message'):
                                    current_app.logger.error(f"  - Error message: {error.message}")
                                if hasattr(error, 'details'):
                                    current_app.logger.error(f"  - Error details: {error.details}")
                                    
                    except Exception as logging_error:
                        if FLASK_AVAILABLE:
                            current_app.logger.error(f"Error while extracting detailed error information: {logging_error}")
                    
                    raise batch_error
                    
            else:
                # SYNCHRONOUS PROCESSING PATH
                print(f"--- [Celery Task] Small document detected ({page_count or 'unknown'} pages) - using SYNCHRONOUS processing")
                
                # For synchronous processing, use processor path WITH version
                processor_path = f"projects/{project_id}/locations/{location}/processors/{processor_id}/processorVersions/pretrained-ocr-v2.0-2023-06-02"
                
                # Read file content
                with open(temp_file_path, "rb") as image:
                    image_content = image.read()
                
                # Create raw document
                raw_document = documentai.RawDocument(
                    content=image_content,
                    mime_type=mime_type
                )
                
                # Create process request
                request = documentai.ProcessRequest(
                    name=processor_path,
                    raw_document=raw_document
                )
                
                print(f"--- [Celery Task] Starting synchronous processing with processor: {processor_path}")
                
                # Process document
                result = client.process_document(request=request)
                document = result.document
                
                # Extract text content
                markdown_content = document.text
                
                print("--- [Celery Task] Synchronous processing completed successfully")
        else:
            print("--- [Celery Task] Starting STANDARD conversion path (markitdown).")
            md = MarkItDown()
            result = md.convert(temp_file_path)
            markdown_content = result.text_content
        
        # Update conversion record with success
        if conversion_id and MODELS_AVAILABLE:
            conversion = Conversion.get_conversion_safely(conversion_id)
            if conversion:
                conversion.status = 'completed'
                conversion.completed_at = datetime.now(timezone.utc)
                conversion.processing_time = time.time() - start_time
                conversion.markdown_length = len(markdown_content) if markdown_content else 0
                
                # Track Pro usage if this was a Pro conversion
                if use_pro_converter and conversion.user_id:
                    user = User.get_user_safely(conversion.user_id)
                    if user:
                        # Use the accurate page count passed to the task
                        if page_count is None:
                            # This should not happen in production, but handle gracefully
                            file_extension = os.path.splitext(original_filename)[1].lower()
                            pages_processed = get_accurate_pdf_page_count(temp_file_path) if file_extension == '.pdf' else 1
                        else:
                            pages_processed = page_count
                        
                        # Only set pages_processed if the column exists
                        try:
                            conversion.pages_processed = pages_processed
                            # Update user's monthly usage
                            current_usage = getattr(user, 'pro_pages_processed_current_month', 0)
                            user.pro_pages_processed_current_month = current_usage + pages_processed
                            print(f"--- [Celery Task] Updated usage: {current_usage} + {pages_processed} = {current_usage + pages_processed}")
                        except Exception as e:
                            print(f"--- [Celery Task] Warning: Could not update pages_processed: {e}")
                
                db.session.commit()
        
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            print("--- [Celery Task] Temporary file cleaned up.")
        
        # Clean up temporary credentials file
        if credentials_path and os.path.exists(credentials_path):
            os.unlink(credentials_path)
            print("--- [Celery Task] Temporary credentials cleaned up.")
        
        print("--- [Celery Task] SUCCESS: Conversion completed successfully.")
        
        return {
            'status': 'SUCCESS',
            'markdown': markdown_content,
            'filename': original_filename
        }
        
    except Exception as e:
        print(f"--- [Celery Task] ERROR: {str(e)}")
        
        # Enhanced error logging for Google Document AI errors
        if "Document AI" in str(e) or "batch processing" in str(e).lower():
            print(f"--- [Celery Task] DETAILED ERROR ANALYSIS:")
            print(f"  - Error type: {type(e).__name__}")
            print(f"  - Error message: {str(e)}")
            
            # Check for Google API specific error attributes
            if hasattr(e, 'code'):
                print(f"  - Google API error code: {e.code}")
            if hasattr(e, 'message'):
                print(f"  - Google API error message: {e.message}")
            if hasattr(e, 'details'):
                print(f"  - Google API error details: {e.details}")
            if hasattr(e, 'reason'):
                print(f"  - Google API error reason: {e.reason}")
            
            # Log additional context
            print(f"  - File: {original_filename}")
            print(f"  - Page count: {page_count}")
            print(f"  - Use Pro converter: {use_pro_converter}")
            print(f"  - Conversion ID: {conversion_id}")
        
        # Update conversion record with failure
        if conversion_id and MODELS_AVAILABLE:
            try:
                conversion = Conversion.get_conversion_safely(conversion_id)
                if conversion:
                    conversion.status = 'failed'
                    conversion.error_message = str(e)
                    conversion.completed_at = datetime.now(timezone.utc)
                    conversion.processing_time = time.time() - start_time
                    db.session.commit()
            except Exception as db_error:
                print(f"--- [Celery Task] Error updating conversion record: {db_error}")
        
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print("--- [Celery Task] Temporary file cleaned up after error.")
            except Exception as cleanup_error:
                print(f"--- [Celery Task] Error cleaning up temporary file: {cleanup_error}")
        
        # Clean up temporary credentials file
        if 'credentials_path' in locals() and credentials_path and os.path.exists(credentials_path):
            try:
                os.unlink(credentials_path)
                print("--- [Celery Task] Temporary credentials cleaned up after error.")
            except Exception as cleanup_error:
                print(f"--- [Celery Task] Error cleaning up temporary credentials: {cleanup_error}")
        
        return {
            'status': 'FAILURE',
            'error': str(e),
            'filename': original_filename
        }
    finally:
        # Clean up temporary files
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"--- [Celery Task] Cleaned up temporary file: {temp_file_path}")
            except Exception as e:
                print(f"--- [Celery Task] Warning: Could not clean up temporary file {temp_file_path}: {e}")
        
        # Clean up temporary credentials file
        if 'credentials_path' in locals() and credentials_path and os.path.exists(credentials_path):
            try:
                os.unlink(credentials_path)
                print(f"--- [Celery Task] Cleaned up temporary credentials file: {credentials_path}")
            except Exception as e:
                print(f"--- [Celery Task] Warning: Could not clean up temporary credentials file {credentials_path}: {e}")


@celery.task
def expire_trials():
    """Expire trials for users whose trial period has ended."""
    from datetime import datetime, timezone
    from sqlalchemy import text
    
    try:
        with current_app.app_context():
            # Check if trial columns exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('on_trial', 'trial_end_date')
            """))
            existing_columns = [row[0] for row in result]
            
            if 'on_trial' not in existing_columns or 'trial_end_date' not in existing_columns:
                print("--- [Celery Task] Trial columns don't exist yet, skipping trial expiration")
                return
            
            # Find users whose trial has expired
            expired_users = User.query.filter(
                User.on_trial == True,
                User.trial_end_date < datetime.now(timezone.utc)
            ).all()
            
            expired_count = 0
            for user in expired_users:
                user.on_trial = False
                user.subscription_status = 'free'
                expired_count += 1
            
            if expired_count > 0:
                db.session.commit()
                print(f"--- [Celery Task] Expired {expired_count} user trials")
            else:
                print("--- [Celery Task] No trials to expire")
                
    except Exception as e:
        print(f"--- [Celery Task] Error expiring trials: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass


@celery.task
def reset_monthly_usage():
    """Reset monthly usage counters for all users."""
    from sqlalchemy import text
    
    try:
        with current_app.app_context():
            # Check if the column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'pro_pages_processed_current_month'
            """))
            
            if not result.fetchone():
                print("--- [Celery Task] pro_pages_processed_current_month column doesn't exist yet, skipping reset")
                return
            
            # Reset all users' monthly page count
            updated_count = User.query.update({
                User.pro_pages_processed_current_month: 0
            })
            
            db.session.commit()
            print(f"--- [Celery Task] Reset monthly usage for {updated_count} users")
                
    except Exception as e:
        print(f"--- [Celery Task] Error resetting monthly usage: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass


@celery.task
def redis_health_check():
    """
    Simple health check task to keep Redis active.
    This task does minimal work but ensures Redis connection is maintained.
    """
    try:
        # Just return a simple status to keep Redis active
        return {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': 'Redis health check completed'
        }
    except Exception as e:
        return {
            'status': 'error',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': str(e)
        }


@celery.task(bind=True)
def process_batch_conversions(self, batch_id):
    """
    Process all conversion jobs in a batch.
    
    Args:
        batch_id (int): The ID of the batch to process.
    """
    try:
        with current_app.app_context():
            # Get the batch and its conversion jobs
            batch = Batch.query.get(batch_id)
            if not batch:
                print(f"--- [Celery Task] Batch {batch_id} not found")
                return
            
            # Update batch status to processing
            batch.status = 'processing'
            db.session.commit()
            
            # Get all queued conversion jobs for this batch
            conversion_jobs = batch.conversion_jobs.filter_by(status='queued').all()
            
            print(f"--- [Celery Task] Processing {len(conversion_jobs)} conversion jobs for batch {batch_id}")
            
            for job in conversion_jobs:
                try:
                    # Mark job as processing
                    job.start_processing()
                    
                    # Simulate file processing (placeholder for actual conversion logic)
                    # In a real implementation, you would:
                    # 1. Retrieve the uploaded file from storage
                    # 2. Process it using your conversion logic
                    # 3. Store the results
                    
                    # For now, we'll simulate processing with a delay
                    import time
                    time.sleep(2)  # Simulate processing time
                    
                    # Simulate successful conversion
                    markdown_content = f"# Converted: {job.original_filename}\n\nThis is simulated markdown content for {job.original_filename}."
                    job.complete_success(markdown_content, pages_processed=1)
                    
                    print(f"--- [Celery Task] Completed job {job.id} for {job.original_filename}")
                    
                except Exception as job_error:
                    print(f"--- [Celery Task] Error processing job {job.id}: {str(job_error)}")
                    job.complete_failure(str(job_error))
                
                # Update batch progress
                batch.update_progress()
            
            print(f"--- [Celery Task] Batch {batch_id} processing completed")
            
    except Exception as e:
        print(f"--- [Celery Task] Error processing batch {batch_id}: {str(e)}")
        try:
            with current_app.app_context():
                batch = Batch.query.get(batch_id)
                if batch:
                    batch.status = 'failed'
                    db.session.commit()
        except:
            pass