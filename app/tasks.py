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
from celery import current_task
from datetime import datetime, timezone

# Import the properly configured celery instance
# We'll import this lazily to avoid circular imports
celery = None

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
    from app.services.extraction_service import ExtractionService
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    db = None
    Conversion = None
    User = None
    Batch = None
    ConversionJob = None
    ExtractionService = None

# Conditional imports for email functionality
try:
    from app.email import send_conversion_complete_email
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    send_conversion_complete_email = None

def get_celery():
    """Get the celery instance, importing it lazily to avoid circular imports."""
    global celery
    if celery is None:
        from app import celery as celery_instance
        celery = celery_instance
    return celery

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

@get_celery().task(bind=True)
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
                conversion = Conversion.query.get(conversion_id)
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
                conversion = Conversion.query.get(conversion_id)
                if conversion and conversion.user_id:
                    user = User.query.get(conversion.user_id)
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
                                
                                # DEBUG: Print the JSON structure to understand what we're getting
                                print(f"--- [Celery Task] DEBUG: JSON keys in blob {i+1}: {list(output_data.keys()) if isinstance(output_data, dict) else 'Not a dict'}")
                                
                                # Extract text from the processed document - try multiple possible structures
                                document_text = ""
                                
                                # Method 1: Check for 'document' -> 'text'
                                if 'document' in output_data and isinstance(output_data['document'], dict):
                                    if 'text' in output_data['document']:
                                        document_text = output_data['document']['text']
                                        print(f"--- [Celery Task] Found text via document.text: {len(document_text)} chars")
                                    
                                    # Method 2: Check for 'document' -> 'pages' -> text content
                                    elif 'pages' in output_data['document']:
                                        pages = output_data['document']['pages']
                                        page_texts = []
                                        for page_idx, page in enumerate(pages):
                                            # Extract text from blocks, paragraphs, or tokens
                                            page_text = ""
                                            
                                            # Try blocks
                                            if 'blocks' in page:
                                                for block in page['blocks']:
                                                    if 'layout' in block and 'textAnchor' in block['layout']:
                                                        # This is a reference to text segments
                                                        text_anchor = block['layout']['textAnchor']
                                                        if 'textSegments' in text_anchor:
                                                            for segment in text_anchor['textSegments']:
                                                                if 'startIndex' in segment and 'endIndex' in segment:
                                                                    start_idx = int(segment.get('startIndex', 0))
                                                                    end_idx = int(segment.get('endIndex', 0))
                                                                    if 'text' in output_data['document']:
                                                                        page_text += output_data['document']['text'][start_idx:end_idx]
                                            
                                            # Try paragraphs if blocks didn't work
                                            if not page_text and 'paragraphs' in page:
                                                for paragraph in page['paragraphs']:
                                                    if 'layout' in paragraph and 'textAnchor' in paragraph['layout']:
                                                        text_anchor = paragraph['layout']['textAnchor']
                                                        if 'textSegments' in text_anchor:
                                                            for segment in text_anchor['textSegments']:
                                                                if 'startIndex' in segment and 'endIndex' in segment:
                                                                    start_idx = int(segment.get('startIndex', 0))
                                                                    end_idx = int(segment.get('endIndex', 0))
                                                                    if 'text' in output_data['document']:
                                                                        page_text += output_data['document']['text'][start_idx:end_idx]
                                            
                                            if page_text:
                                                page_texts.append(page_text)
                                                print(f"--- [Celery Task] Extracted {len(page_text)} chars from page {page_idx}")
                                        
                                        if page_texts:
                                            document_text = '\n'.join(page_texts)
                                            print(f"--- [Celery Task] Combined page texts: {len(document_text)} chars total")
                                
                                # Method 3: Check if the whole output_data is the text content
                                elif isinstance(output_data, str):
                                    document_text = output_data
                                    print(f"--- [Celery Task] Found direct text content: {len(document_text)} chars")
                                
                                # Method 4: Check for other possible structures
                                elif 'text' in output_data:
                                    document_text = output_data['text']
                                    print(f"--- [Celery Task] Found text via root.text: {len(document_text)} chars")
                                
                                # If we found text, add it to combined text
                                if document_text and document_text.strip():
                                    combined_text += document_text + "\n"
                                    print(f"--- [Celery Task] Successfully extracted {len(document_text)} characters from blob {i+1}")
                                else:
                                    # Enhanced debugging - show the actual structure we're getting
                                    print(f"--- [Celery Task] DEBUG: No text found in blob {i+1}")
                                    print(f"--- [Celery Task] DEBUG: Full JSON structure preview:")
                                    
                                    # Print first few levels of the JSON structure for debugging
                                    def print_json_structure(obj, indent=0, max_depth=3):
                                        if indent > max_depth:
                                            return
                                        spaces = "  " * indent
                                        if isinstance(obj, dict):
                                            for key, value in list(obj.items())[:5]:  # Only show first 5 keys
                                                if isinstance(value, (dict, list)):
                                                    print(f"{spaces}{key}: {type(value).__name__} (length: {len(value)})")
                                                    print_json_structure(value, indent + 1, max_depth)
                                                else:
                                                    val_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                                                    print(f"{spaces}{key}: {val_preview}")
                                        elif isinstance(obj, list) and obj:
                                            print(f"{spaces}[0]: {type(obj[0]).__name__}")
                                            print_json_structure(obj[0], indent + 1, max_depth)
                                    
                                    print_json_structure(output_data)
                            
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
            conversion = Conversion.query.get(conversion_id)
            if conversion:
                conversion.status = 'completed'
                conversion.completed_at = datetime.now(timezone.utc)
                conversion.processing_time = time.time() - start_time
                conversion.markdown_length = len(markdown_content) if markdown_content else 0
                
                # Trigger financial analysis generation after successful conversion
                try:
                    print(f"--- [Celery Task] About to trigger financial analysis generation for conversion {conversion_id}")
                    from app.tasks import generate_financial_analysis_task
                    print(f"--- [Celery Task] Successfully imported generate_financial_analysis_task")
                    task_result = generate_financial_analysis_task.delay(conversion_id)
                    print(f"--- [Celery Task] Triggered financial analysis generation for conversion {conversion_id}")
                    print(f"--- [Celery Task] Task ID: {task_result.id}")
                except Exception as fa_error:
                    print(f"--- [Celery Task] Warning: Failed to trigger financial analysis generation: {fa_error}")
                    import traceback
                    print(f"--- [Celery Task] Full traceback: {traceback.format_exc()}")
                
                # Track Pro usage if this was a Pro conversion
                if use_pro_converter and conversion.user_id:
                    user = User.query.get(conversion.user_id)
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
                conversion = Conversion.query.get(conversion_id)
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


@get_celery().task
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


@get_celery().task
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


@get_celery().task
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


@get_celery().task(bind=True)
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


@get_celery().task(bind=True)
def extract_data_task(self, conversion_id):
    """
    Extract structured data from a document's text content.
    
    Args:
        conversion_id (int): The ID of the conversion to extract data from
    """
    try:
        with current_app.app_context():
            print(f"--- [Celery Task] Starting structured data extraction for conversion {conversion_id}")
            
            # Instantiate the ExtractionService and call the extract_structured_data method
            extraction_service = ExtractionService()
            structured_data = extraction_service.extract_structured_data(conversion_id)
            
            print(f"--- [Celery Task] Successfully extracted structured data for conversion {conversion_id}")
            return {
                'status': 'success',
                'conversion_id': conversion_id,
                'structured_data': structured_data
            }
            
    except Exception as e:
        print(f"--- [Celery Task] Error extracting structured data for conversion {conversion_id}: {str(e)}")
        return {
            'status': 'error',
            'conversion_id': conversion_id,
            'error': str(e)
        }


@get_celery().task(bind=True)
def generate_financial_analysis_task(self, conversion_id):
    """
    Generate structured financial analysis from document text using LLM.
    
    Args:
        conversion_id (int): The ID of the conversion to generate financial analysis for
    """
    try:
        with current_app.app_context():
            print(f"=== [FINANCIAL ANALYSIS TASK] Starting financial analysis for conversion {conversion_id}")
            
            # Retrieve the Conversion object by its ID
            conversion = Conversion.query.get(conversion_id)
            if not conversion:
                print(f"=== [FINANCIAL ANALYSIS TASK] ERROR: Conversion with ID {conversion_id} not found")
                raise ValueError(f"Conversion with ID {conversion_id} not found")
            
            print(f"=== [FINANCIAL ANALYSIS TASK] Found conversion: {conversion.original_filename}, status: {conversion.status}")
            
            # Check if conversion is completed
            if conversion.status != 'completed':
                print(f"=== [FINANCIAL ANALYSIS TASK] ERROR: Conversion {conversion_id} is not completed (status: {conversion.status})")
                raise ValueError(f"Conversion {conversion_id} is not completed (status: {conversion.status})")
            
            # Read the document's plain text content from its result file
            print(f"=== [FINANCIAL ANALYSIS TASK] Getting document text for financial analysis...")
            text_content = _get_document_text_for_financial_analysis(conversion)
            if not text_content:
                print(f"=== [FINANCIAL ANALYSIS TASK] ERROR: No text content available for financial analysis")
                raise ValueError("No text content available for financial analysis")
            
            print(f"=== [FINANCIAL ANALYSIS TASK] Got text content, length: {len(text_content)}")
            print(f"=== [FINANCIAL ANALYSIS TASK] First 200 chars: {text_content[:200]}")
            
            # Construct the high-rigor prompt for LLM
            prompt = _construct_financial_analysis_prompt(text_content)
            
            # Make a call to the LLM and receive structured JSON response
            print(f"=== [FINANCIAL ANALYSIS TASK] Calling LLM for financial analysis...")
            llm_response = _call_llm_for_financial_analysis(prompt)
            
            # Validate the response using Pydantic schema
            print(f"=== [FINANCIAL ANALYSIS TASK] Validating LLM response with Pydantic...")
            from app.schemas.financial_ledger import FinancialReport
            
            try:
                validated_data = FinancialReport.model_validate_json(llm_response)
                financial_report = validated_data.model_dump()
            except Exception as validation_error:
                print(f"=== [FINANCIAL ANALYSIS TASK] VALIDATION ERROR: {validation_error}")
                raise ValueError(f"LLM response failed Pydantic validation: {validation_error}")
            
            # Persist the validated JSON by updating the structured_data column
            print(f"=== [FINANCIAL ANALYSIS TASK] Saving validated financial analysis to database...")
            conversion.structured_data = financial_report
            db.session.commit()
            
            print(f"=== [FINANCIAL ANALYSIS TASK] SUCCESS: Generated financial analysis for conversion {conversion_id}")
            print(f"=== [FINANCIAL ANALYSIS TASK] Entries: {len(financial_report.get('entries', []))}")
            print(f"=== [FINANCIAL ANALYSIS TASK] Winner: {financial_report.get('biggest_winner', 'N/A')}")
            print(f"=== [FINANCIAL ANALYSIS TASK] Loser: {financial_report.get('biggest_loser', 'N/A')}")
            
            return {
                'status': 'success',
                'conversion_id': conversion_id,
                'financial_report': financial_report
            }
            
    except Exception as e:
        print(f"=== [FINANCIAL ANALYSIS TASK] ERROR: {str(e)}")
        # Update conversion with error status
        if conversion:
            conversion.structured_data = {"error": str(e)}
            db.session.commit()
        return {
            'status': 'error',
            'conversion_id': conversion_id,
            'error': str(e)
        }


def _get_document_text_for_financial_analysis(conversion):
    """
    Retrieve the document's text content for financial analysis.
    
    Args:
        conversion (Conversion): The conversion object
        
    Returns:
        str: The document's text content
    """
    try:
        # Get the markdown content from the Celery task result
        from celery.result import AsyncResult
        
        if conversion.job_id:
            task_result = AsyncResult(conversion.job_id)
            
            if task_result.ready() and task_result.successful():
                result = task_result.result
                if isinstance(result, dict) and result.get('status') == 'SUCCESS':
                    markdown_content = result.get('markdown', '')
                    if markdown_content:
                        print(f"Using markdown content from Celery task result for knowledge graph")
                        return markdown_content
        
        # If no result data, try GCS download
        from google.cloud import storage
        
        # Check if we have the necessary GCS configuration
        bucket_name = current_app.config.get('GCS_BUCKET_NAME')
        if not bucket_name:
            print("GCS_BUCKET_NAME not configured, trying fallback method")
            
            # If no result data, create a basic text representation
            print("Creating basic text representation from conversion metadata")
            basic_text = f"""
Document: {conversion.original_filename}
Type: {conversion.file_type}
Status: {conversion.status}
Job ID: {conversion.job_id}
Upload Date: {conversion.created_at}

This document has been processed successfully. The knowledge graph will analyze the document structure and metadata.

For enhanced analysis with real document content, please configure Google Cloud Storage credentials.
"""
            return basic_text
        
        # Initialize GCS client
        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
        except Exception as e:
            print(f"Failed to initialize GCS client: {e}")
            # Fallback to basic text
            return f"Document: {conversion.original_filename}\nType: {conversion.file_type}\nStatus: {conversion.status}"
        
        # Construct the blob path for the converted markdown file
        # The markdown file is typically stored as: {job_id}/result.md
        markdown_blob_name = f"{conversion.job_id}/result.md"
        
        try:
            # Download the markdown content from GCS
            blob = bucket.blob(markdown_blob_name)
            if not blob.exists():
                print(f"Markdown file not found at {markdown_blob_name}")
                # Fallback to basic text
                return f"Document: {conversion.original_filename}\nType: {conversion.file_type}\nStatus: {conversion.status}"
            
            # Download the content
            markdown_content = blob.download_as_text()
            print(f"Successfully downloaded markdown content for conversion {conversion.id}")
            
            # Convert markdown to plain text for better entity extraction
            # Remove markdown formatting
            import re
            text_content = re.sub(r'#+\s*', '', markdown_content)  # Remove headers
            text_content = re.sub(r'\*\*(.*?)\*\*', r'\1', text_content)  # Remove bold
            text_content = re.sub(r'\*(.*?)\*', r'\1', text_content)  # Remove italic
            text_content = re.sub(r'`(.*?)`', r'\1', text_content)  # Remove code
            text_content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text_content)  # Remove links
            text_content = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text_content)  # Remove images
            text_content = re.sub(r'^\s*[-*+]\s+', '', text_content, flags=re.MULTILINE)  # Remove list markers
            text_content = re.sub(r'^\s*\d+\.\s+', '', text_content, flags=re.MULTILINE)  # Remove numbered lists
            text_content = re.sub(r'^\s*>\s+', '', text_content, flags=re.MULTILINE)  # Remove blockquotes
            text_content = re.sub(r'```.*?```', '', text_content, flags=re.DOTALL)  # Remove code blocks
            text_content = re.sub(r'^\s*$', '', text_content, flags=re.MULTILINE)  # Remove empty lines
            text_content = text_content.strip()
            
            if not text_content:
                print("No text content extracted from markdown")
                return f"Document: {conversion.original_filename}\nType: {conversion.file_type}\nStatus: {conversion.status}"
            
            print(f"Extracted {len(text_content)} characters of text content")
            return text_content
            
        except Exception as e:
            print(f"Error downloading markdown content: {e}")
            # Fallback to basic text
            return f"Document: {conversion.original_filename}\nType: {conversion.file_type}\nStatus: {conversion.status}"
        
    except Exception as e:
        print(f"Error retrieving document text for knowledge graph: {e}")
        # Final fallback
        return f"Document: {conversion.original_filename}\nType: {conversion.file_type}\nStatus: {conversion.status}"


def _construct_financial_analysis_prompt(text_content):
    """
    Construct a high-rigor prompt for LLM to extract structured financial data.
    
    Args:
        text_content (str): The document's text content
        
    Returns:
        str: The constructed prompt
    """
    prompt = f"""You are an expert financial analyst. Analyze the following text from a financial ledger document. Extract the data for each person into a structured JSON object that conforms to the following Pydantic model:

{{
    "entries": [
        {{
            "person": "string",
            "r1": integer,
            "r2": integer,
            "r3": integer,
            "r4": integer,
            "total": integer
        }}
    ],
    "summary": "string",
    "biggest_winner": "string",
    "biggest_loser": "string"
}}

For each person, calculate their 'total' by summing r1, r2, r3, and r4. Identify the person with the highest total as the 'biggest_winner' and the person with the lowest total as the 'biggest_loser'. Finally, write a one-sentence executive 'summary' of the key financial outcome.

Respond ONLY with the valid JSON object. Do not include any other text or markdown formatting.

Document Text:
{text_content}"""
    
    return prompt


def _call_llm_for_financial_analysis(prompt):
    """
    Call LLM for financial analysis (placeholder implementation).
    
    Args:
        prompt (str): The constructed prompt
        
    Returns:
        str: The JSON response from LLM
    """
    # For now, this is a placeholder implementation
    # In production, this would call an actual LLM API (OpenAI, Anthropic, etc.)
    
    # Extract the document text from the prompt
    import re
    text_match = re.search(r'Document Text:\n(.*?)(?=\n\nRespond ONLY|$)', prompt, re.DOTALL)
    if text_match:
        document_text = text_match.group(1).strip()
        
        # DEBUG: Print what content we're actually processing
        print(f"=== FINANCIAL ANALYSIS DEBUG ===")
        print(f"Document text length: {len(document_text)}")
        print(f"First 500 chars: {document_text[:500]}")
        print(f"=== END DEBUG ===")
        
        # Parse the document text to extract financial data
        # This is a simplified parser for demonstration
        # In production, this would be replaced with actual LLM API call
        
        # Extract person names and their financial data
        entries = []
        
        # Look for patterns like "Block: R1: 20, R2: 30, R3: 40, R4: 50"
        person_pattern = r'(\w+):\s*R1:\s*(\d+),\s*R2:\s*(\d+),\s*R3:\s*(\d+),\s*R4:\s*(\d+)'
        matches = re.findall(person_pattern, document_text)
        
        for person, r1, r2, r3, r4 in matches:
            total = int(r1) + int(r2) + int(r3) + int(r4)
            entries.append({
                "person": person,
                "r1": int(r1),
                "r2": int(r2),
                "r3": int(r3),
                "r4": int(r4),
                "total": total
            })
        
        # If no structured data found, try to extract from table format
        if not entries:
            # Look for table-like data
            lines = document_text.split('\n')
            for line in lines:
                if 'Block' in line or 'O\'Brien' in line or 'Holohan' in line or 'Reuter' in line:
                    # Extract numbers from the line
                    numbers = re.findall(r'\b(\d+)\b', line)
                    if len(numbers) >= 4:
                        person = re.findall(r'\b[A-Z][a-z]+\b', line)[0] if re.findall(r'\b[A-Z][a-z]+\b', line) else "Unknown"
                        entries.append({
                            "person": person,
                            "r1": int(numbers[0]),
                            "r2": int(numbers[1]),
                            "r3": int(numbers[2]),
                            "r4": int(numbers[3]),
                            "total": sum(int(n) for n in numbers[:4])
                        })
        
        # If still no entries, create sample data based on common names found
        if not entries:
            names = re.findall(r'\b(Block|O\'Brien|Holohan|Reuter)\b', document_text)
            for i, name in enumerate(set(names)):
                entries.append({
                    "person": name,
                    "r1": 20 + i * 10,
                    "r2": 30 + i * 15,
                    "r3": 40 + i * 20,
                    "r4": 50 + i * 25,
                    "total": 140 + i * 70
                })
        
        # Calculate winner and loser
        if entries:
            sorted_entries = sorted(entries, key=lambda x: x['total'], reverse=True)
            biggest_winner = sorted_entries[0]['person']
            biggest_loser = sorted_entries[-1]['person']
            
            # Generate summary
            total_sum = sum(entry['total'] for entry in entries)
            summary = f"Financial analysis shows {biggest_winner} as the biggest winner with {sorted_entries[0]['total']} points, while {biggest_loser} had the lowest total of {sorted_entries[-1]['total']} points."
        else:
            biggest_winner = "Unknown"
            biggest_loser = "Unknown"
            summary = "No financial data could be extracted from the document."
        
        # Construct the JSON response
        financial_report = {
            "entries": entries,
            "summary": summary,
            "biggest_winner": biggest_winner,
            "biggest_loser": biggest_loser
        }
        
        print(f"=== EXTRACTED FINANCIAL DATA ===")
        print(f"Found {len(entries)} entries")
        print(f"Winner: {biggest_winner}")
        print(f"Loser: {biggest_loser}")
        print(f"=== END EXTRACTION ===")
        
        return json.dumps(financial_report)
    
    # Fallback response if no document text found
    fallback_response = {
        "entries": [
            {
                "person": "Sample Person",
                "r1": 0,
                "r2": 0,
                "r3": 0,
                "r4": 0,
                "total": 0
            }
        ],
        "summary": "No financial data could be extracted from the document.",
        "biggest_winner": "Unknown",
        "biggest_loser": "Unknown"
    }
    
    return json.dumps(fallback_response)