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
from app import celery, db
from flask import current_app
from app.models import Conversion, User, Batch, ConversionJob
from app.email import send_conversion_complete_email
from datetime import datetime, timezone

# Configuration constants
MONTHLY_PAGE_ALLOWANCE = 1000  # Pages per month for Pro users

# Configuration constants
MONTHLY_PAGE_ALLOWANCE = 1000  # Pages per month for Pro users

# Configuration constants
MONTHLY_PAGE_ALLOWANCE = 1000  # Pages per month for Pro users

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
            current_app.logger.info(f"Virus scan passed for file: {file_path}")
            return True, "File scanned successfully, no threats detected"
        elif result.returncode == 1:
            # Virus detected
            current_app.logger.error(f"VIRUS DETECTED in file: {file_path}")
            current_app.logger.error(f"ClamAV output: {result.stdout}")
            return False, f"Virus detected: {result.stdout.strip()}"
        else:
            # Scan error
            current_app.logger.error(f"Virus scan error for file: {file_path}")
            current_app.logger.error(f"ClamAV error: {result.stderr}")
            return False, f"Virus scan error: {result.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        current_app.logger.error(f"Virus scan timeout for file: {file_path}")
        return False, "Virus scan timeout"
    except Exception as e:
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
            current_app.logger.info(f"Accurate PDF page count: {page_count} pages")
            return page_count
            
    except ImportError:
        current_app.logger.error("pypdf library not available - this should not happen in production")
        raise Exception("PDF page counting library not available. Please contact support.")
    except Exception as e:
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
        processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
        
        print("--- [Celery Task] Sending request to Google Document AI API...")
        
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document
        
        return document.text
        
    except Exception as e:
        print(f"--- [Celery Task] Document AI API error: {str(e)}")
        raise e

def process_with_docai_batch(credentials_path, project_id, location, processor_id, input_gcs_uri, output_gcs_uri):
    """
    Process large documents using Google Document AI batch processing.

    Args:
        credentials_path (str): Path to the service account credentials JSON file.
        project_id (str): Google Cloud project ID.
        location (str): Processor region.
        processor_id (str): Document AI processor ID.
        input_gcs_uri (str): GCS URI for input files.
        output_gcs_uri (str): GCS URI for output files.

    Returns:
        str: Extracted text content from the document.

    Raises:
        Exception: If the Document AI API call fails.
    """
    print("--- [Celery Task] Inside process_with_docai_batch helper function.")
    opts = {"api_endpoint": f"{location}-documentai.googleapis.com"}
    
    try:
        # Load credentials from file for batch processing
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        
        client = documentai.DocumentProcessorServiceClient(
            client_options=opts,
            credentials=credentials
        )
        
        processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
        
        # Configure the batch process request with correct API structure
        input_config = documentai.BatchDocumentsInputConfig(
            gcs_source=input_gcs_uri,
            mime_type="application/pdf"
        )
        
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=output_gcs_uri
            )
        )
        
        request = documentai.BatchProcessRequest(
            name=processor_name,
            input_documents=input_config,
            document_output_config=output_config
        )
        
        print("--- [Celery Task] Starting batch processing...")
        
        # Start the batch process
        operation = client.batch_process_documents(request=request)
        
        print("--- [Celery Task] Waiting for batch processing to complete...")
        
        # Wait for the operation to complete
        operation.result()
        
        print("--- [Celery Task] Batch processing completed.")
        
        # Download and process the results
        storage_client = storage.Client.from_service_account_json(credentials_path)
        bucket = storage_client.bucket(project_id)
        
        # List all output files
        blobs = bucket.list_blobs(prefix=output_gcs_uri.replace(f"gs://{project_id}/", ""))
        
        combined_text = ""
        for blob in blobs:
            if blob.name.endswith('.json'):
                # Download and parse the JSON result
                content = blob.download_as_text()
                result = json.loads(content)
                
                # Extract text from the result
                if 'document' in result and 'text' in result['document']:
                    combined_text += result['document']['text'] + "\n"
        
        return combined_text.strip()
        
    except Exception as e:
        print(f"--- [Celery Task] Document AI batch processing error: {str(e)}")
        raise e

@celery.task(bind=True)
def convert_file_task(self, bucket_name, blob_name, original_filename, use_pro_converter=False, conversion_id=None, page_count=None):
    """
    Celery task to perform file conversion, update the Conversion record, and handle errors robustly.
    Enhanced with virus scanning and security logging.

    Args:
        self: Celery task instance (provided by Celery).
        bucket_name (str): Name of the GCS bucket.
        blob_name (str): Name of the blob in the bucket.
        original_filename (str): Original filename of the uploaded file.
        use_pro_converter (bool, optional): Whether to use the Pro (Document AI) converter. Defaults to False.
        conversion_id (int, optional): ID of the Conversion record to update. Defaults to None.
        page_count (int, optional): Accurate page count for PDF files. Defaults to None.

    Returns:
        dict: Result dictionary with status, markdown content (if successful), and filename.
    """
    print("\n\n--- [Celery Task] NEW TASK RECEIVED ---")
    print(f"    Filename: '{original_filename}' | Pro mode: {use_pro_converter} | Pages: {page_count}")
    temp_file_path = None
    start_time = time.time()
    
    try:
        with current_app.app_context():
            # Get credentials
            print("--- [Celery Task] DEBUG: Getting credentials...")
            credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if credentials_path:
                # Create temporary credentials file
                credentials_json = credentials_path
                temp_creds = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                temp_creds.write(credentials_json)
                temp_creds.close()
                credentials_path = temp_creds.name
                print(f"--- [Celery Task] Explicitly using credentials from: {credentials_path}")
            else:
                raise Exception("Google Cloud credentials not found")
            
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
                current_app.logger.error(f"SECURITY EVENT: Virus detected in file {original_filename}")
                current_app.logger.error(f"Scan result: {scan_result}")
                
                # Update conversion record with failure
                if conversion_id:
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
                    current_app.logger.info(f"Deleted infected file: {temp_file_path}")
                except Exception as e:
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
                if conversion_id:
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
                            current_app.logger.warning("No page count passed to task - getting from file")
                            file_extension = os.path.splitext(original_filename)[1].lower()
                            if file_extension == '.pdf':
                                page_count = get_accurate_pdf_page_count(temp_file_path)
                            else:
                                page_count = 1  # Images and other files count as 1 page
                        
                        # Check if this job would exceed the monthly limit
                        if current_usage + page_count > MONTHLY_PAGE_ALLOWANCE:
                            remaining_pages = MONTHLY_PAGE_ALLOWANCE - current_usage
                            raise Exception(f"Monthly limit exceeded. This job would use {page_count} pages, but you only have {remaining_pages} pages remaining this month. Please upgrade to Pro+ or wait until next month's reset.")
                        
                        print(f"--- [Celery Task] Usage check passed: {current_usage} + {page_count} = {current_usage + page_count} pages (limit: {MONTHLY_PAGE_ALLOWANCE})")
                
                # Check if file type is supported by Document AI
                file_extension = os.path.splitext(original_filename)[1].lower()
                docai_supported_types = {'.pdf', '.gif', '.tiff', '.tif', '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.html'}
                
                if file_extension not in docai_supported_types:
                    print(f"--- [Celery Task] File type {file_extension} not supported by Document AI, falling back to standard converter")
                    print("--- [Celery Task] Starting STANDARD conversion path (markitdown).")
                    md = MarkItDown()
                    result = md.convert(temp_file_path)
                    markdown_content = result.text_content
                else:
                    print("--- [Celery Task] Starting PRO conversion path (Document AI).")
                    
                    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'mdraft')
                    location = os.environ.get('DOCAI_PROCESSOR_REGION', 'us')
                    processor_id = os.environ.get('DOCAI_PROCESSOR_ID')
                    
                    print(f"Using Project ID: {project_id} | Location: {location} | Processor ID: {processor_id}")
                    
                    # Determine MIME type based on file extension
                    mime_type_map = {
                        '.pdf': 'application/pdf',
                        '.png': 'image/png',
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif',
                        '.bmp': 'image/bmp',
                        '.tiff': 'image/tiff',
                        '.tif': 'image/tiff',
                        '.webp': 'image/webp',
                        '.html': 'text/html'
                    }
                    mime_type = mime_type_map.get(file_extension, 'application/pdf')
                    
                    # Only use page count for PDFs
                    if file_extension == '.pdf':
                        # Use the accurate page count passed to the task
                        if page_count is None:
                            # This should not happen in production, but handle gracefully
                            current_app.logger.warning("No page count passed to task - getting from file")
                            file_extension = os.path.splitext(original_filename)[1].lower()
                            if file_extension == '.pdf':
                                page_count = get_accurate_pdf_page_count(temp_file_path)
                            else:
                                page_count = 1  # Images and other files count as 1 page
                        
                        print(f"--- [Celery Task] Using accurate page count: {page_count} pages")
                        print(f"--- [Celery Task] DEBUG: File size: {file_size} bytes")
                        
                        # Google Document AI sync API has a 10-page limit
                        # Use batch processing for documents > 10 pages
                        if page_count > 10:
                            print(f"--- [Celery Task] Large document detected ({page_count} pages) - using BATCH processing")
                            
                            # Create unique GCS paths for batch processing
                            batch_id = str(uuid.uuid4())
                            print(f"--- [Celery Task] DEBUG: Generated batch ID: {batch_id}")
                            
                            # Upload file to GCS input location for batch processing
                            input_blob_name = f"batch-input/{batch_id}/{original_filename}"
                            print(f"--- [Celery Task] DEBUG: Uploading to batch input: {input_blob_name}")
                            input_blob = bucket.blob(input_blob_name)
                            input_blob.upload_from_filename(temp_file_path)
                            
                            input_gcs_uri = f"gs://{bucket_name}/batch-input/{batch_id}/"
                            output_gcs_uri = f"gs://{bucket_name}/batch-output/{batch_id}/"
                            print(f"--- [Celery Task] DEBUG: Input URI: {input_gcs_uri}")
                            print(f"--- [Celery Task] DEBUG: Output URI: {output_gcs_uri}")
                            
                            # Process with batch API
                            markdown_content = process_with_docai_batch(
                                credentials_path, project_id, location, processor_id,
                                input_gcs_uri, output_gcs_uri
                            )
                            
                            # Clean up batch files
                            try:
                                for blob_cleanup in bucket.list_blobs(prefix=f"batch-input/{batch_id}/"):
                                    blob_cleanup.delete()
                                for blob_cleanup in bucket.list_blobs(prefix=f"batch-output/{batch_id}/"):
                                    blob_cleanup.delete()
                            except:
                                pass  # Don't fail the task if cleanup fails
                            
                        else:
                            print(f"--- [Celery Task] Small document ({page_count} pages) - using synchronous processing")
                            # Use existing synchronous processing for small files
                            markdown_content = process_with_docai(
                                credentials_path, project_id, location, processor_id, 
                                temp_file_path, mime_type
                            )
                    else:
                        # For images and HTML, use synchronous processing
                        print("--- [Celery Task] Image/HTML file - using synchronous processing")
                        markdown_content = process_with_docai(
                            credentials_path, project_id, location, processor_id, 
                            temp_file_path, mime_type
                        )
            else:
                print("--- [Celery Task] Starting STANDARD conversion path (markitdown).")
                md = MarkItDown()
                result = md.convert(temp_file_path)
                markdown_content = result.text_content
            
            if conversion_id:
                conversion = Conversion.get_conversion_safely(conversion_id)
                if conversion:
                    conversion.status = 'completed'
                    conversion.completed_at = datetime.now(timezone.utc)
                    conversion.processing_time = time.time() - start_time
                    conversion.markdown_length = len(markdown_content)
                    
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
        
        # Update conversion record with failure
        if conversion_id:
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