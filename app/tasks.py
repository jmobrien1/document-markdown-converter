# app/tasks.py
# Complete file with Document AI batch processing for large PDFs - FINAL VERSION

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
from app import celery
from flask import current_app

def get_pdf_page_count(file_path):
    """Estimate PDF page count using simple heuristic."""
    try:
        # Simple heuristic: file size estimation
        # Rough estimate: 1 page ≈ 50-100KB for typical PDFs
        file_size = os.path.getsize(file_path)
        estimated_pages = max(1, file_size // 70000)  # Conservative estimate
        return estimated_pages
    except:
        return 1  # Default to 1 page if estimation fails

def process_with_docai(credentials_path, project_id, location, processor_id, file_path, mime_type):
    """Helper function to call the Document AI API for synchronous processing."""
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
    """Process large documents using Document AI batch processing."""
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
        
        # Input and output configuration
        input_config = documentai.BatchDocumentsInputConfig(
            gcs_prefix=documentai.GcsPrefix(gcs_uri_prefix=input_gcs_uri)
        )
        
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.GcsOutputConfig(
                gcs_uri=output_gcs_uri
            )
        )
        
        # Create batch process request
        request = documentai.BatchProcessRequest(
            name=processor_name,
            input_documents=input_config,
            document_output_config=output_config,
        )
        
        print(f"--- [Celery Task] Submitting batch job for processor: {processor_name}")
        
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
        
        # Download the processed results from GCS
        storage_client = storage.Client.from_service_account_json(credentials_path)
        
        # The output will be in the specified GCS output location
        # Document AI creates JSON files with the extracted text
        bucket_name = output_gcs_uri.split('/')[2]
        output_prefix = '/'.join(output_gcs_uri.split('/')[3:])
        
        bucket = storage_client.bucket(bucket_name)
        
        # List files in output directory
        blobs = bucket.list_blobs(prefix=output_prefix)
        
        extracted_text = ""
        for blob in blobs:
            if blob.name.endswith('.json'):
                # Download and parse the JSON result
                json_content = blob.download_as_text()
                doc_data = json.loads(json_content)
                
                # Extract text from Document AI response
                if 'document' in doc_data and 'text' in doc_data['document']:
                    extracted_text += doc_data['document']['text']
                    extracted_text += "\n\n"
        
        if not extracted_text.strip():
            raise Exception("No text extracted from batch processing results")
        
        print(f"--- [Celery Task] Successfully extracted {len(extracted_text)} characters from batch processing")
        return extracted_text.strip()
        
    except Exception as e:
        print(f"--- [Celery Task] Batch processing error: {str(e)}")
        raise Exception(f"Document AI batch processing failed: {str(e)}")

@celery.task(bind=True)
def convert_file_task(self, bucket_name, blob_name, original_filename, use_pro_converter=False):
    """Enhanced Celery task with batch processing for large documents."""
    print("\n\n--- [Celery Task] NEW TASK RECEIVED ---")
    print(f"    Filename: '{original_filename}' | Pro mode: {use_pro_converter}")
    
    temp_file_path = None
    
    try:
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
            print("--- [Celery Task] Starting PRO conversion path (Document AI).")
            
            project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'mdraft')
            location = os.environ.get('DOCAI_PROCESSOR_REGION', 'us')
            processor_id = os.environ.get('DOCAI_PROCESSOR_ID')
            
            print(f"Using Project ID: {project_id} | Location: {location} | Processor ID: {processor_id}")
            
            # DEBUG: Check if this is a large PDF that needs batch processing
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
                    temp_file_path, "application/pdf"
                )
        else:
            print("--- [Celery Task] Starting STANDARD conversion path (markitdown).")
            md = MarkItDown()
            result = md.convert(temp_file_path)
            markdown_content = result.text_content
        
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