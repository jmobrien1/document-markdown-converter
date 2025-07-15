import os
import subprocess
import tempfile
from flask import Flask, request, render_template, jsonify, send_file, session
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'txt', 'html', 'htm', 'csv', 'json', 'xml', 'epub', 'mp3', 'wav', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'zip'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main page with upload form"""
    return render_template('index.html')

@app.route('/test')
def test_route():
    """Simple test to verify Flask is working"""
    return '<h1>Flask is working!</h1><p>Routes are accessible.</p>'

@app.route('/convert', methods=['POST'])
def convert_file():
    """Handle file upload and conversion using Python API"""
    print("=== CONVERT ROUTE CALLED ===")
    
    try:
        if 'file' not in request.files:
            print("ERROR: No file in request")
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['file']
        file_size = len(file.read())
        file.seek(0)  # Reset file pointer after reading size
        
        print(f"File received: {file.filename}, size: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
        
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            print(f"ERROR: File type not allowed: {file.filename}")
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Check file size limits
        if file_size > 5 * 1024 * 1024:  # 5MB limit for now
            print(f"ERROR: File too large: {file_size} bytes")
            return jsonify({'error': 'File too large. Please use files under 5MB.'}), 400
        
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        print(f"Saving file to: {file_path}")
        
        # Save uploaded file
        file.save(file_path)
        print("File saved successfully")
        
        # Try using markitdown Python API with timeout handling
        print("Starting markitdown conversion...")
        try:
            from markitdown import MarkItDown
            print("MarkItDown imported successfully")
            
            md = MarkItDown()
            print("MarkItDown instance created")
            
            # Set timeout based on file size
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Conversion timed out")
            
            # Calculate timeout: 30 seconds base + 10 seconds per MB
            timeout_seconds = 30 + int(file_size / (1024 * 1024)) * 10
            timeout_seconds = min(timeout_seconds, 120)  # Max 2 minutes
            
            print(f"Setting timeout to {timeout_seconds} seconds")
            
            # Set signal alarm for timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            
            try:
                result = md.convert(file_path)
                signal.alarm(0)  # Cancel alarm
                
                print(f"Conversion completed. Text length: {len(result.text_content) if result.text_content else 0}")
                
            except TimeoutError:
                signal.alarm(0)  # Cancel alarm
                os.remove(file_path)
                print("ERROR: Conversion timed out")
                return jsonify({'error': f'Conversion timed out after {timeout_seconds} seconds. Try a smaller or simpler file.'}), 500
            
            # Clean up uploaded file
            os.remove(file_path)
            print("Uploaded file cleaned up")
            
            if result.text_content:
                print("Conversion successful, preparing response...")
                
                # Store markdown content for download
                download_id = str(uuid.uuid4())
                temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
                
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    f.write(result.text_content)
                
                print("Response prepared successfully")
                
                # For very large results, be more aggressive with truncation
                content_length = len(result.text_content)
                if content_length > 10000:
                    preview = result.text_content[:1500] + f"\n\n[Content truncated - showing 1,500 of {content_length:,} characters. Download for full content.]"
                elif content_length > 2000:
                    preview = result.text_content[:2000] + f"\n\n[Content truncated - showing 2,000 of {content_length:,} characters. Download for full content.]"
                else:
                    preview = result.text_content
                
                return jsonify({
                    'success': True,
                    'markdown': preview,
                    'download_id': download_id,
                    'original_filename': filename,
                    'full_length': content_length,
                    'is_truncated': content_length > 2000
                })
            else:
                print("ERROR: No content extracted from file")
                return jsonify({'error': 'No content extracted from file'}), 500
                
        except ImportError as e:
            os.remove(file_path)
            print(f"ERROR: Cannot import MarkItDown: {str(e)}")
            return jsonify({'error': f'MarkItDown not available: {str(e)}'}), 500
            
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            print(f"ERROR: MarkItDown processing failed: {str(e)}")
            return jsonify({'error': f'Conversion failed: {str(e)}'}), 500
            
    except Exception as e:
        print(f"ERROR: Unexpected error: {str(e)}")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/download/<download_id>')
def download_file(download_id):
    """Download converted markdown file"""
    try:
        temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
        
        if not os.path.exists(temp_file_path):
            return jsonify({'error': 'File not found or expired'}), 404
        
        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name='mdraft_output.ml',
            mimetype='text/plain'
        )
        
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

@app.route('/test-markitdown')
def test_markitdown():
    """Test if markitdown is working"""
    try:
        # First test: CLI command
        result = subprocess.run(['markitdown', '--help'], capture_output=True, text=True, timeout=5)
        cli_working = True
        cli_output = result.stdout[:500]
    except subprocess.TimeoutExpired:
        cli_working = False
        cli_output = "CLI command timed out"
    except FileNotFoundError:
        cli_working = False
        cli_output = "CLI command not found"
    except Exception as e:
        cli_working = False
        cli_output = f"CLI error: {str(e)}"
    
    # Second test: Python import
    try:
        from markitdown import MarkItDown
        python_import = True
        python_error = None
        
        # Try to create instance
        md = MarkItDown()
        instance_created = True
    except ImportError as e:
        python_import = False
        python_error = f"Import error: {str(e)}"
        instance_created = False
    except Exception as e:
        python_import = True
        python_error = f"Instance error: {str(e)}"
        instance_created = False
    
    return jsonify({
        'cli_available': cli_working,
        'cli_output': cli_output,
        'python_import': python_import,
        'python_error': python_error,
        'instance_created': instance_created
    })

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 10MB.'}), 413

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)