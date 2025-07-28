# app/tasks.py
# Complete file with Document AI batch processing and fixed text extraction

import os
import time
import tempfile
import json
import uuid
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

def get_pdf_page_count(file_path):
    """
    Estimate PDF page count using a simple file size heuristic.

    Args:
        file_path (str): Path to the PDF file.

    Returns:
        int: Estimated number of pages in the PDF.
    """
    try:
        # Simple heuristic: file size estimation
        # Rough estimate: 1 page ≈ 50-100KB for typical PDFs
        file_size = os.path.getsize(file_path)
        estimated_pages = max(1, file_size // 70000)  # Conservative estimate
        return estimated_pages
    except:
        return 1  # Default to 1 page if estimation fails

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
        str: Extracted text content from the batch processing results.

    Raises:
        Exception: If batch processing fails or no text is extracted.
    """
    print("--- [Celery Task] Starting Document AI BATCH processing...")
    
    try:
        # Initialize Document AI client with proper credentials
        client_options = {"api_endpoint": f"{location}-documentai.googleapis.com"}
        
        # Load credentials from file
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        
        client = documentai.DocumentProcessorServiceClient(
            client_options=client_options,
            credentials=credentials
        )
        
        # Prepare batch processing request
        processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
        
        # Create the batch process request using correct structure
        request = {
            "name": processor_name,
            "input_documents": {
                "gcs_prefix": {
                    "gcs_uri_prefix": input_gcs_uri
                }
            },
            "document_output_config": {
                "gcs_output_config": {
                    "gcs_uri": output_gcs_uri
                }
            }
        }
        
        print(f"--- [Celery Task] Submitting batch job for processor: {processor_name}")
        print(f"--- [Celery Task] DEBUG: Input URI: {input_gcs_uri}")
        print(f"--- [Celery Task] DEBUG: Output URI: {output_gcs_uri}")
        
        # Submit batch processing job
        operation = client.batch_process_documents(request=request)
        
        print(f"--- [Celery Task] Batch job submitted. Operation name: {operation.operation.name}")
        
        # Update task progress
        current_task.update_state(
            state='PROGRESS',
            meta={'status': 'Large document submitted for batch processing...'}
        )
        
        # Poll for completion (with timeout)
        max_wait_time = 600  # 10 minutes max wait
        poll_interval = 30   # Check every 30 seconds
        elapsed_time = 0
        
        while not operation.done() and elapsed_time < max_wait_time:
            print(f"--- [Celery Task] Batch processing in progress... ({elapsed_time}s)")
            current_task.update_state(
                state='PROGRESS',
                meta={'status': f'Processing large document... ({elapsed_time // 60}m {elapsed_time % 60}s)'}
            )
            time.sleep(poll_interval)
            elapsed_time += poll_interval
        
        if not operation.done():
            raise Exception("Batch processing timed out after 10 minutes")
        
        print("--- [Celery Task] Batch processing completed!")
        
        # Get the result
        result = operation.result()
        print(f"--- [Celery Task] DEBUG: Operation result type: {type(result)}")
        
        # Download the processed results from GCS
        storage_client = storage.Client.from_service_account_json(credentials_path)
        
        # The output will be in the specified GCS output location
        bucket_name = output_gcs_uri.split('/')[2]
        output_prefix = '/'.join(output_gcs_uri.split('/')[3:])
        
        print(f"--- [Celery Task] DEBUG: Looking for output files in bucket: {bucket_name}")
        print(f"--- [Celery Task] DEBUG: Output prefix: {output_prefix}")
        
        bucket = storage_client.bucket(bucket_name)
        
        # List ALL files in output directory
        blobs = list(bucket.list_blobs(prefix=output_prefix))
        print(f"--- [Celery Task] DEBUG: Found {len(blobs)} files in output directory")
        
        for blob in blobs:
            print(f"--- [Celery Task] DEBUG: Found file: {blob.name} (size: {blob.size} bytes)")
        
        extracted_text = ""
        json_files_found = 0
        
        for blob in blobs:
            if blob.name.endswith('.json'):
                json_files_found += 1
                print(f"--- [Celery Task] DEBUG: Processing JSON file: {blob.name}")
                
                try:
                    # Download and parse the JSON result
                    json_content = blob.download_as_text()
                    print(f"--- [Celery Task] DEBUG: Downloaded JSON content length: {len(json_content)}")
                    
                    doc_data = json.loads(json_content)
                    print(f"--- [Celery Task] DEBUG: JSON keys: {list(doc_data.keys())}")
                    
                    # Extract text from Document AI batch response
                    # The text is directly in the 'text' field for batch processing
                    if 'text' in doc_data:
                        text_content = doc_data['text']
                        print(f"--- [Celery Task] DEBUG: Found text content, length: {len(text_content)}")
                        extracted_text += text_content
                        extracted_text += "\n\n"
                    elif 'document' in doc_data and 'text' in doc_data['document']:
                        # Fallback for synchronous format
                        text_content = doc_data['document']['text']
                        print(f"--- [Celery Task] DEBUG: Found text content in document.text, length: {len(text_content)}")
                        extracted_text += text_content
                        extracted_text += "\n\n"
                    else:
                        print(f"--- [Celery Task] DEBUG: No text field found in JSON structure")
                        # Show what structure we do have
                        if 'document' in doc_data:
                            print(f"--- [Celery Task] DEBUG: Document keys: {list(doc_data['document'].keys())}")
                        else:
                            print(f"--- [Celery Task] DEBUG: Available top-level keys: {list(doc_data.keys())}")
                        
                except Exception as e:
                    print(f"--- [Celery Task] DEBUG: Error processing JSON file {blob.name}: {e}")
        
        print(f"--- [Celery Task] DEBUG: Processed {json_files_found} JSON files")
        print(f"--- [Celery Task] DEBUG: Total extracted text length: {len(extracted_text)}")
        
        if not extracted_text.strip():
            # More detailed error information
            error_msg = f"No text extracted from batch processing results. Found {len(blobs)} files, {json_files_found} JSON files"
            if blobs:
                error_msg += f". Files found: {[blob.name for blob in blobs[:5]]}"  # Show first 5 files
            raise Exception(error_msg)
        
        print(f"--- [Celery Task] Successfully extracted {len(extracted_text)} characters from batch processing")
        return extracted_text.strip()
        
    except Exception as e:
        print(f"--- [Celery Task] Batch processing error: {str(e)}")
        raise Exception(f"Document AI batch processing failed: {str(e)}")

@celery.task(bind=True)
def convert_file_task(self, bucket_name, blob_name, original_filename, use_pro_converter=False, conversion_id=None):
    """
    Celery task to perform file conversion, update the Conversion record, and handle errors robustly.

    Args:
        self: Celery task instance (provided by Celery).
        bucket_name (str): Name of the GCS bucket.
        blob_name (str): Name of the blob in the bucket.
        original_filename (str): Original filename of the uploaded file.
        use_pro_converter (bool, optional): Whether to use the Pro (Document AI) converter. Defaults to False.
        conversion_id (int, optional): ID of the Conversion record to update. Defaults to None.

    Returns:
        dict: Result dictionary with status, markdown content (if successful), and filename.
    """
    print("\n\n--- [Celery Task] NEW TASK RECEIVED ---")
    print(f"    Filename: '{original_filename}' | Pro mode: {use_pro_converter}")
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
                        
                        # Estimate pages for this job
                        file_extension = os.path.splitext(original_filename)[1].lower()
                        if file_extension == '.pdf':
                            estimated_pages = get_pdf_page_count(temp_file_path)
                        else:
                            estimated_pages = 1  # Images and other files count as 1 page
                        
                        # Check if this job would exceed the monthly limit
                        if current_usage + estimated_pages > MONTHLY_PAGE_ALLOWANCE:
                            remaining_pages = MONTHLY_PAGE_ALLOWANCE - current_usage
                            raise Exception(f"Monthly limit exceeded. This job would use {estimated_pages} pages, but you only have {remaining_pages} pages remaining this month. Please upgrade to Pro+ or wait until next month's reset.")
                        
                        print(f"--- [Celery Task] Usage check passed: {current_usage} + {estimated_pages} = {current_usage + estimated_pages} pages (limit: {MONTHLY_PAGE_ALLOWANCE})")
                
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
                    
                    # Only use page estimation for PDFs
                    if file_extension == '.pdf':
                        print("--- [Celery Task] DEBUG: Calling get_pdf_page_count...")
                        estimated_pages = get_pdf_page_count(temp_file_path)
                        print(f"--- [Celery Task] Estimated pages: {estimated_pages}")
                        print(f"--- [Celery Task] DEBUG: File size used for estimation: {file_size}")
                        print(f"--- [Celery Task] DEBUG: Calculation: {file_size} / 70000 = {file_size // 70000}")
                        
                        if estimated_pages > 25:  # Use batch processing for files likely >30 pages
                            print("--- [Celery Task] Large document detected - using BATCH processing")
                            
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
                            print("--- [Celery Task] Small document - using synchronous processing")
                            print(f"--- [Celery Task] DEBUG: {estimated_pages} <= 25, using sync processing")
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
                            # Estimate pages processed (for now, use file size heuristic)
                            pages_processed = get_pdf_page_count(temp_file_path) if file_extension == '.pdf' else 1
                            # Only set pages_processed if the column exists
                            try:
                                conversion.pages_processed = pages_processed
                            except:
                                pass  # Column doesn't exist yet
                            
                            # Atomically increment user's monthly usage
                            try:
                                user.pro_pages_processed_current_month += pages_processed
                                print(f"--- [Celery Task] Tracked {pages_processed} pages for user {user.email}")
                            except:
                                pass  # Column doesn't exist yet
                    
                    db.session.commit()
                    
                    # Send email notification if user is logged in
                    if conversion.user_id:
                        try:
                            user = User.get_user_safely(conversion.user_id)
                            if user and user.email:
                                send_conversion_complete_email(user.email, original_filename)
                        except Exception as e:
                            print(f"--- [Celery Task] Email notification failed: {str(e)}")
                            # Don't fail the task if email fails
        print("--- [Celery Task] Conversion completed successfully!")
        return {
            'status': 'SUCCESS',
            'markdown': markdown_content,
            'filename': original_filename
        }
    except Exception as e:
        error_msg = str(e)
        print(f"--- [Celery Task] !!! AN ERROR OCCURRED !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {error_msg}")
        with current_app.app_context():
            if conversion_id:
                conversion = Conversion.get_conversion_safely(conversion_id)
                if conversion:
                    conversion.status = 'failed'
                    conversion.error_message = error_msg
                    db.session.commit()
        return {
            'status': 'FAILURE',
            'error': f'A server error occurred: {type(e).__name__}'
        }
    finally:
        # Cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        if 'temp_creds' in locals() and os.path.exists(temp_creds.name):
            os.unlink(temp_creds.name)
        print("--- [Celery Task] Cleanup complete. Task finished. ---\n")


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