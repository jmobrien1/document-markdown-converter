import os
import subprocess
import tempfile
from flask import Flask, request, render_template, jsonify, send_file
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = './uploads'

# mdraft app configuration
app.config['APP_NAME'] = 'mdraft'
app.config['APP_VERSION'] = '1.0.0'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_markdown(file_path):
    """Convert file to markdown using markitdown CLI"""
    try:
        # Run markitdown command and capture output
        result = subprocess.run(
            ['markitdown', file_path],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return None, f"Conversion error: {e.stderr}"
    except FileNotFoundError:
        return None, "markitdown not found. Please install it with: pip install markitdown"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

@app.route('/')
def index():
    """Main page with upload form"""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    """Handle file upload and conversion"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Please upload PDF or DOCX files only.'}), 400
    
    try:
        # Generate unique filename to avoid conflicts
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save uploaded file
        file.save(file_path)
        
        # Convert to markdown
        markdown_content, error = convert_to_markdown(file_path)
        
        # Clean up uploaded file
        os.remove(file_path)
        
        if error:
            return jsonify({'error': error}), 500
        
        # Store markdown content in session or temporary file for download
        session_id = str(uuid.uuid4())
        temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{session_id}.ml")
        
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        return jsonify({
            'success': True,
            'markdown': markdown_content,
            'download_id': session_id,
            'original_filename': filename
        })
        
    except Exception as e:
        # Clean up file if it exists
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

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
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)