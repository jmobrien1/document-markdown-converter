# app/tasks.py
# This version explicitly loads the service account file to bypass environment issues.

import os
import tempfile
from google.cloud import storage, documentai
from google.api_core import exceptions as google_exceptions
from app import celery
from markitdown import MarkItDown
from flask import current_app

def process_with_docai(credentials_path, project_id, location, processor_id, file_path, mime_type):
    """Helper function to call the Document AI API."""
    print("--- [Celery Task] Inside process_with_docai helper function.")
    opts = {"api_endpoint": f"{location}-documentai.googleapis.com"}
    
    # --- THE FIX: Explicitly use credentials from the specified file path ---
    docai_client = documentai.DocumentProcessorServiceClient.from_service_account_file(credentials_path, client_options=opts)
    
    name = docai_client.processor_path(project_id, location, processor_id)
    with open(file_path, "rb") as image:
        image_content = image.read()
    raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    
    print("--- [Celery Task] Sending request to Google Document AI API...")
    result = docai_client.process_document(request=request)
    return result.document.text


@celery.task(bind=True)
def convert_file_task(self, bucket_name, blob_name, original_filename, use_pro_converter=False):
    """Celery task to download a file from GCS, convert it, and clean up."""
    print("\n\n--- [Celery Task] NEW TASK RECEIVED ---")
    print(f"    Filename: '{original_filename}' | Pro mode: {use_pro_converter}")
    
    temp_file_path = None
    try:
        credentials_path = current_app.config.get('GCS_CREDENTIALS_PATH')
        if not credentials_path or not os.path.exists(credentials_path):
             raise FileNotFoundError(f"Credentials file not found at path: {credentials_path}. Check .env and config.py.")

        print(f"--- [Celery Task] Explicitly using credentials from: {credentials_path}")
        
        # --- THE FIX: Explicitly use credentials from the specified file path ---
        storage_client = storage.Client.from_service_account_json(credentials_path)
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        _, temp_file_path = tempfile.mkstemp()
        blob.download_to_filename(temp_file_path)
        print("--- [Celery Task] File downloaded from GCS successfully.")
        
        final_text = ""
        if use_pro_converter:
            print("--- [Celery Task] Starting PRO conversion path (Document AI).")
            # We can now get the project ID directly from the authenticated client
            project_id = storage_client.project
            location = current_app.config.get('DOCAI_PROCESSOR_REGION')
            processor_id = current_app.config.get('DOCAI_PROCESSOR_ID')
            
            print(f"    Using Project ID: {project_id} | Location: {location} | Processor ID: {processor_id}")
            if not all([project_id, location, processor_id]):
                raise ValueError("Missing GCS/DocAI configuration values.")

            mime_type = 'application/pdf'
            final_text = process_with_docai(credentials_path, project_id, location, processor_id, temp_file_path, mime_type)
        else:
            # Standard conversion remains the same
            print("--- [Celery Task] Starting STANDARD conversion path (markitdown).")
            md = MarkItDown()
            result = md.convert(temp_file_path)
            final_text = result.text_content if result else ""

        if final_text:
            return_dict = {'status': 'SUCCESS', 'markdown': final_text, 'original_filename': original_filename}
            return return_dict
        else:
            return {'status': 'FAILURE', 'error': 'Conversion failed: No content could be extracted.'}
            
    except Exception as e:
        print(f"--- [Celery Task] !!! AN ERROR OCCURRED !!!")
        print(f"    Error Type: {type(e).__name__}")
        print(f"    Error Details: {e}")
        return {'status': 'FAILURE', 'error': f'A server error occurred: {type(e).__name__}'}
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        
        try:
            # Re-initialize client to be safe for cleanup
            credentials_path = current_app.config.get('GCS_CREDENTIALS_PATH')
            if credentials_path and os.path.exists(credentials_path):
                storage_client = storage.Client.from_service_account_json(credentials_path)
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                if blob.exists():
                    blob.delete()
        except Exception:
            pass
        print("--- [Celery Task] Cleanup complete. Task finished. ---\n")