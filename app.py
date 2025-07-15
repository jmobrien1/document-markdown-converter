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

@app.route('/debug-convert', methods=['POST'])
def debug_convert():
    """Step-by-step debug conversion with status reporting"""
    print("=== DEBUG CONVERT STARTED ===")
    
    status = {"step": 1, "message": "Starting debug conversion", "success": True}
    file_path = None
    
    try:
        # Step 1: Check file upload
        if 'file' not in request.files:
            return jsonify({"step": 1, "error": "No file in request", "success": False})
        
        file = request.files['file']
        file_size = len(file.read())
        file.seek(0)
        
        status.update({"step": 2, "message": f"File received: {file.filename} ({file_size} bytes)"})
        print(f"DEBUG: {status['message']}")
        
        # Step 2: Validate file
        if file.filename == '':
            return jsonify({"step": 2, "error": "Empty filename", "success": False})
        
        if not allowed_file(file.filename):
            return jsonify({"step": 2, "error": f"File type not allowed: {file.filename}", "success": False})
        
        status.update({"step": 3, "message": "File validation passed"})
        print(f"DEBUG: {status['message']}")
        
        # Step 3: Save file
        filename = secure_filename(file.filename)
        unique_filename = f"debug_{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        
        status.update({"step": 4, "message": f"File saved to: {file_path}"})
        print(f"DEBUG: {status['message']}")
        
        # Step 4: Test markitdown import
        try:
            from markitdown import MarkItDown
            status.update({"step": 5, "message": "MarkItDown imported successfully"})
            print(f"DEBUG: {status['message']}")
        except Exception as e:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"step": 5, "error": f"Import failed: {str(e)}", "success": False})
        
        # Step 5: Create MarkItDown instance
        try:
            md = MarkItDown()
            status.update({"step": 6, "message": "MarkItDown instance created"})
            print(f"DEBUG: {status['message']}")
        except Exception as e:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"step": 6, "error": f"Instance creation failed: {str(e)}", "success": False})
        
        # Step 6: Try conversion with very short timeout
        status.update({"step": 7, "message": "Starting conversion (10 second timeout)..."})
        print(f"DEBUG: {status['message']}")
        
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Debug conversion timed out")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)  # Very short timeout for debugging
        
        try:
            result = md.convert(file_path)
            signal.alarm(0)  # Cancel alarm
            
            if result and result.text_content:
                content_length = len(result.text_content)
                status.update({
                    "step": 8, 
                    "message": f"Conversion successful! Generated {content_length} characters",
                    "content_preview": result.text_content[:200] + "..." if content_length > 200 else result.text_content,
                    "full_length": content_length
                })
            else:
                status.update({"step": 8, "message": "Conversion completed but no content generated"})
                
        except TimeoutError:
            signal.alarm(0)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"step": 7, "error": "Conversion timed out after 10 seconds", "success": False})
        except Exception as e:
            signal.alarm(0)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"step": 7, "error": f"Conversion failed: {str(e)}", "success": False})
        
        # Step 7: Cleanup
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        status.update({"step": 9, "message": "Debug conversion completed successfully"})
        print(f"DEBUG: {status['message']}")
        
        return jsonify(status)
        
    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"step": status.get("step", 0), "error": f"Unexpected error: {str(e)}", "success": False})

@app.route('/convert', methods=['POST'])
def convert_file():
    """Simple convert route for working conversions"""
    print("=== CONVERT ROUTE CALLED ===")
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['file']
        file_size = len(file.read())
        file.seek(0)
        
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file'}), 400
        
        # Only process small files for now
        if file_size > 500 * 1024:  # 500KB limit for regular conversion
            return jsonify({'error': 'File too large for regular conversion. Try the debug conversion or use a smaller file.'}), 400
        
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        
        os.remove(file_path)
        
        if result and result.text_content:
            download_id = str(uuid.uuid4())
            temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
            
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write(result.text_content)
            
            return jsonify({
                'success': True,
                'markdown': result.text_content[:1500] + "..." if len(result.text_content) > 1500 else result.text_content,
                'download_id': download_id,
                'original_filename': filename,
                'full_length': len(result.text_content)
            })
        else:
            return jsonify({'error': 'No content extracted'}), 500
            
    except Exception as e:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

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

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 10MB.'}), 413

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)