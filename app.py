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
    """Handle file upload and conversion"""
    print("=== CONVERT ROUTE CALLED ===")  # Debug log
    
    try:
        if 'file' not in request.files:
            print("ERROR: No file in request")
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['file']
        print(f"File received: {file.filename}, size: {len(file.read())} bytes")
        file.seek(0)  # Reset file pointer after reading size
        
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            print(f"ERROR: File type not allowed: {file.filename}")
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        print(f"Saving file to: {file_path}")
        
        # Save uploaded file
        file.save(file_path)
        print("File saved successfully")
        
        # Check if markitdown is available
        print("Testing markitdown availability...")
        try:
            test_result = subprocess.run(['markitdown', '--help'], capture_output=True, text=True, timeout=5)
            print(f"Markitdown test result: {test_result.returncode}")
        except FileNotFoundError:
            os.remove(file_path)
            print("ERROR: markitdown command not found")
            return jsonify({'error': 'markitdown is not installed on the server'}), 500
        except Exception as e:
            os.remove(file_path)
            print(f"ERROR: markitdown test failed: {str(e)}")
            return jsonify({'error': f'markitdown test failed: {str(e)}'}), 500
        
        print("Starting conversion...")
        
        # Convert using markitdown
        result = subprocess.run(
            ['markitdown', file_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(f"Conversion completed. Return code: {result.returncode}")
        print(f"STDOUT length: {len(result.stdout)}")
        print(f"STDERR: {result.stderr}")
        
        # Clean up uploaded file
        os.remove(file_path)
        print("Uploaded file cleaned up")
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown conversion error"
            print(f"ERROR: Conversion failed: {error_msg}")
            return jsonify({'error': f'Conversion failed: {error_msg}'}), 500
        
        if result.stdout:
            print("Conversion successful, preparing response...")
            
            # Store markdown content for download
            download_id = str(uuid.uuid4())
            temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
            
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            
            print("Response prepared successfully")
            
            return jsonify({
                'success': True,
                'markdown': result.stdout[:1000] + "..." if len(result.stdout) > 1000 else result.stdout,  # Truncate for response
                'download_id': download_id,
                'original_filename': filename,
                'full_length': len(result.stdout)
            })
        else:
            print("ERROR: No content extracted from file")
            return jsonify({'error': 'No content extracted from file'}), 500
            
    except subprocess.TimeoutExpired:
        print("ERROR: Conversion timed out")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': 'Conversion timed out (60 seconds)'}), 500
        
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
        result = subprocess.run(['markitdown', '--help'], capture_output=True, text=True, timeout=10)
        return jsonify({
            'markitdown_available': True,
            'help_output': result.stdout[:500]
        })
    except FileNotFoundError:
        return jsonify({'markitdown_available': False, 'error': 'markitdown command not found'})
    except Exception as e:
        return jsonify({'markitdown_available': False, 'error': str(e)})

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 10MB.'}), 413

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)