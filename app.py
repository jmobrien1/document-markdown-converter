import os
import subprocess
import tempfile
import threading
import time
from flask import Flask, request, render_template, jsonify, send_file, session
from werkzeug.utils import secure_filename
import uuid
import sqlite3
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Reduce to 10MB for better performance
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# mdraft app configuration
app.config['APP_NAME'] = 'mdraft'
app.config['APP_VERSION'] = '1.0.0'
app.config['DATABASE'] = 'mdraft.db'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_database():
    """Initialize the SQLite database with user and usage tables"""
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT DEFAULT 'free',
            is_verified INTEGER DEFAULT 0
        )
    ''')
    
    # Daily usage tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            date DATE,
            conversions_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, date),
            UNIQUE(session_id, date)
        )
    ''')
    
    # Conversion history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            filename TEXT,
            file_type TEXT,
            file_size INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user_by_email(email):
    """Get user by email address"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"Database error in get_user_by_email: {e}")
        return None

def create_user(email):
    """Create a new user account"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (email) VALUES (?)', (email,))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # User already exists
    except Exception as e:
        print(f"Database error in create_user: {e}")
        return None

def get_daily_usage(user_id=None, session_id=None):
    """Get today's usage count for user or session"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        today = datetime.now().date()
        
        if user_id:
            cursor.execute(
                'SELECT conversions_count FROM daily_usage WHERE user_id = ? AND date = ?',
                (user_id, today)
            )
        else:
            cursor.execute(
                'SELECT conversions_count FROM daily_usage WHERE session_id = ? AND date = ?',
                (session_id, today)
            )
        
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        print(f"Database error in get_daily_usage: {e}")
        return 0

def increment_usage(user_id=None, session_id=None):
    """Increment today's usage count"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        today = datetime.now().date()
        
        if user_id:
            cursor.execute('''
                INSERT OR REPLACE INTO daily_usage (user_id, date, conversions_count)
                VALUES (?, ?, COALESCE((SELECT conversions_count FROM daily_usage WHERE user_id = ? AND date = ?), 0) + 1)
            ''', (user_id, today, user_id, today))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO daily_usage (session_id, date, conversions_count)
                VALUES (?, ?, COALESCE((SELECT conversions_count FROM daily_usage WHERE session_id = ? AND date = ?), 0) + 1)
            ''', (session_id, today, session_id, today))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database error in increment_usage: {e}")

def log_conversion(user_id, session_id, filename, file_type, file_size, status):
    """Log conversion attempt"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversions (user_id, session_id, filename, file_type, file_size, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, session_id, filename, file_type, file_size, status))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database error in log_conversion: {e}")

def check_usage_limit(user_id=None, session_id=None):
    """Check if user/session has reached daily limit"""
    if user_id:
        # Registered users get unlimited conversions (for now)
        return True
    else:
        # Anonymous users get 5 conversions per day
        usage = get_daily_usage(session_id=session_id)
        return usage < 5

# Initialize database on startup
init_database()
# Allowed file extensions - markitdown supports many formats
ALLOWED_EXTENSIONS = {
    # Office Documents
    'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx',
    # Text & Data Formats
    'txt', 'html', 'htm', 'csv', 'json', 'xml', 'epub',
    # Multimedia
    'mp3', 'wav', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff',
    # Archives
    'zip'
}

@app.route('/signup', methods=['POST'])
def signup():
    """Create a new user account"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email or '@' not in email:
        return jsonify({'error': 'Valid email address required'}), 400
    
    # Check if user already exists
    existing_user = get_user_by_email(email)
    if existing_user:
        # Log them in instead
        session['user_id'] = existing_user[0]
        session['user_email'] = existing_user[1]
        return jsonify({
            'success': True,
            'message': 'Welcome back! You are now signed in.',
            'user': {'email': existing_user[1], 'plan': existing_user[3]}
        })
    
    # Create new user
    user_id = create_user(email)
    if user_id:
        session['user_id'] = user_id
        session['user_email'] = email
        return jsonify({
            'success': True,
            'message': 'Account created successfully! You now have unlimited conversions.',
            'user': {'email': email, 'plan': 'free'}
        })
    else:
        return jsonify({'error': 'Failed to create account'}), 500

@app.route('/login', methods=['POST'])
def login():
    """Simple email-based login"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'error': 'Email address required'}), 400
    
    user = get_user_by_email(email)
    if user:
        session['user_id'] = user[0]
        session['user_email'] = user[1]
        return jsonify({
            'success': True,
            'message': 'Welcome back!',
            'user': {'email': user[1], 'plan': user[3]}
        })
    else:
        return jsonify({'error': 'Account not found. Please sign up first.'}), 404

@app.route('/logout', methods=['POST'])
def logout():
    """Log out current user"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/user-status')
def user_status():
    """Get current user status and usage"""
    try:
        # Initialize database if it doesn't exist
        init_database()
        
        session_id = session.get('session_id', str(uuid.uuid4()))
        session['session_id'] = session_id
        
        user_id = session.get('user_id')
        
        if user_id:
            # Logged in user
            user = get_user_by_email(session.get('user_email'))
            if user:
                usage = get_daily_usage(user_id=user_id)
                return jsonify({
                    'logged_in': True,
                    'user': {'email': user[1], 'plan': user[3]},
                    'daily_usage': usage,
                    'daily_limit': 'unlimited',
                    'remaining': 'unlimited'
                })
            else:
                # User not found, clear session
                session.clear()
        
        # Anonymous user or cleared session
        session_id = session.get('session_id', str(uuid.uuid4()))
        session['session_id'] = session_id
        usage = get_daily_usage(session_id=session_id)
        return jsonify({
            'logged_in': False,
            'daily_usage': usage,
            'daily_limit': 5,
            'remaining': max(0, 5 - usage)
        })
        
    except Exception as e:
        print(f"Error in user_status: {e}")
        # Return safe defaults
        return jsonify({
            'logged_in': False,
            'daily_usage': 0,
            'daily_limit': 5,
            'remaining': 5
        })

def get_session_id():
    """Get or create session ID"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Global dict to track conversion jobs
conversion_jobs = {}

def convert_to_markdown_async(job_id, file_path):
    """Convert file to markdown asynchronously"""
    try:
        conversion_jobs[job_id] = {'status': 'processing', 'progress': 0, 'result': None, 'error': None}
        
        # Get file info
        file_size = os.path.getsize(file_path)
        file_ext = file_path.rsplit('.', 1)[1].lower() if '.' in file_path else ''
        
        # Update progress
        conversion_jobs[job_id]['progress'] = 10
        
        # Determine timeout
        if file_ext == 'pdf':
            if file_size > 5 * 1024 * 1024:  # 5MB+
                timeout = 300  # 5 minutes for large PDFs
            elif file_size > 2 * 1024 * 1024:  # 2MB+
                timeout = 180  # 3 minutes for medium PDFs
            else:
                timeout = 120  # 2 minutes for small PDFs
        else:
            timeout = 60  # 1 minute for other formats
        
        conversion_jobs[job_id]['progress'] = 20
        
        # Run conversion
        result = subprocess.run(
            ['markitdown', file_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        
        conversion_jobs[job_id]['progress'] = 90
        
        # Success
        conversion_jobs[job_id].update({
            'status': 'completed',
            'progress': 100,
            'result': result.stdout,
            'error': None
        })
        
    except subprocess.TimeoutExpired:
        conversion_jobs[job_id].update({
            'status': 'failed',
            'progress': 100,
            'error': f"Conversion timed out after {timeout} seconds. Try a smaller file."
        })
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or str(e)
        conversion_jobs[job_id].update({
            'status': 'failed',
            'progress': 100,
            'error': f"Conversion error: {error_msg}"
        })
    except Exception as e:
        conversion_jobs[job_id].update({
            'status': 'failed',
            'progress': 100,
            'error': f"Unexpected error: {str(e)}"
        })
    finally:
        # Clean up file
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/')
def index():
    """Main page with upload form"""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    """Handle file upload and conversion - simplified for debugging"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Please upload supported formats: PDF, DOCX, XLSX, PPTX, TXT, HTML, CSV, JSON, XML, MP3, Images, ZIP, and more.'}), 400
    
    # Get user/session info
    user_id = session.get('user_id')
    session_id = get_session_id()
    
    # Check usage limits
    if not check_usage_limit(user_id, session_id):
        return jsonify({
            'error': 'Daily limit reached! Sign up for unlimited conversions.',
            'limit_reached': True,
            'daily_limit': 5
        }), 429
    
    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file_size = len(file.read())
        file.seek(0)  # Reset file pointer
        
        # Save uploaded file
        file.save(file_path)
        
        # Get file type for logging
        file_type = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
        
        # For small PDFs (< 1MB), process synchronously for now
        if file_type == 'pdf' and file_size < 1024 * 1024:
            try:
                # Direct conversion for small files
                result = subprocess.run(
                    ['markitdown', file_path],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60  # 1 minute timeout for small files
                )
                
                # Clean up uploaded file
                os.remove(file_path)
                
                if result.stdout:
                    # Success - log and return result
                    log_conversion(user_id, session_id, filename, file_type, file_size, 'success')
                    increment_usage(user_id, session_id)
                    
                    # Store markdown content for download
                    download_id = str(uuid.uuid4())
                    temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
                    
                    with open(temp_file_path, 'w', encoding='utf-8') as f:
                        f.write(result.stdout)
                    
                    # Get updated usage for response
                    new_usage = get_daily_usage(user_id, session_id)
                    remaining = 'unlimited' if user_id else max(0, 5 - new_usage)
                    
                    return jsonify({
                        'success': True,
                        'markdown': result.stdout,
                        'download_id': download_id,
                        'original_filename': filename,
                        'usage_info': {
                            'daily_usage': new_usage,
                            'remaining': remaining,
                            'is_logged_in': bool(user_id)
                        }
                    })
                else:
                    os.remove(file_path)
                    return jsonify({'error': 'No content extracted from PDF'}), 500
                    
            except subprocess.TimeoutExpired:
                os.remove(file_path)
                return jsonify({'error': 'PDF conversion timed out. Please try a simpler PDF.'}), 500
            except subprocess.CalledProcessError as e:
                os.remove(file_path)
                error_msg = e.stderr or str(e)
                return jsonify({'error': f'PDF conversion failed: {error_msg}'}), 500
            except Exception as e:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({'error': f'PDF processing error: {str(e)}'}), 500
        
        else:
            # For larger files or other formats, use async processing
            job_id = str(uuid.uuid4())
            
            # Start async conversion
            thread = threading.Thread(target=convert_to_markdown_async, args=(job_id, file_path))
            thread.daemon = True
            thread.start()
            
            # Log conversion start and increment usage
            log_conversion(user_id, session_id, filename, file_type, file_size, 'started')
            increment_usage(user_id, session_id)
            
            # Return job ID for polling
            return jsonify({
                'success': True,
                'job_id': job_id,
                'filename': filename,
                'status': 'processing'
            })
        
    except Exception as e:
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

@app.route('/test-page')
def test_page():
    """Minimal test page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>mdraft Test</title></head>
    <body style="background: red; color: white; padding: 20px;">
        <h1>TEST PAGE WORKING</h1>
        <p>If you see this, the new code deployed successfully.</p>
        <form enctype="multipart/form-data" method="post" action="/simple-convert">
            <input type="file" name="file" required>
            <button type="submit">Test Upload</button>
        </form>
        <script>
            console.log("Test page JavaScript is working");
            alert("Test page loaded successfully!");
        </script>
    </body>
    </html>
    '''
def health_check():
    """Simple health check with timestamp"""
    from datetime import datetime
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': 'debug-2025-07-15',
        'routes_available': ['/convert', '/simple-convert', '/test-markitdown', '/debug-jobs']
    })
def simple_convert():
    """Ultra simple conversion for debugging"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file in request', 'debug': True}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Empty filename', 'debug': True}), 400
        
        # Just return file info without processing
        return jsonify({
            'success': True,
            'debug': True,
            'filename': file.filename,
            'size': len(file.read()),
            'content_type': file.content_type,
            'message': 'File received successfully (not processed)'
        })
        
    except Exception as e:
        return jsonify({'error': f'Exception: {str(e)}', 'debug': True}), 500
def test_markitdown():
    """Test if markitdown is working"""
    try:
        result = subprocess.run(['markitdown', '--help'], capture_output=True, text=True, timeout=10)
        return jsonify({
            'markitdown_available': True,
            'help_output': result.stdout[:500],  # First 500 chars
            'error': result.stderr[:200] if result.stderr else None
        })
    except subprocess.TimeoutExpired:
        return jsonify({'markitdown_available': False, 'error': 'markitdown command timed out'})
    except FileNotFoundError:
        return jsonify({'markitdown_available': False, 'error': 'markitdown command not found'})
    except Exception as e:
        return jsonify({'markitdown_available': False, 'error': str(e)})
def debug_jobs():
    """Debug route to see active conversion jobs"""
    return jsonify({
        'active_jobs': list(conversion_jobs.keys()),
        'job_details': {k: {'status': v['status'], 'progress': v['progress']} for k, v in conversion_jobs.items()}
    })
@app.route('/job-status/<job_id>')
def job_status(job_id):
    """Check conversion job status"""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = conversion_jobs[job_id]
    
    if job['status'] == 'completed':
        # Store result for download
        temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{job_id}.ml")
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(job['result'])
        
        # Clean up job
        del conversion_jobs[job_id]
        
        return jsonify({
            'status': 'completed',
            'progress': 100,
            'download_id': job_id,
            'markdown': job['result']
        })
    
    elif job['status'] == 'failed':
        error = job['error']
        # Clean up job
        del conversion_jobs[job_id]
        
        return jsonify({
            'status': 'failed',
            'progress': 100,
            'error': error
        })
    
    else:
        return jsonify({
            'status': job['status'],
            'progress': job['progress']
        })

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
    # Railway provides PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    # Ensure we bind to all interfaces for Railway
    app.run(debug=False, host='0.0.0.0', port=port)
else:
    # For production WSGI servers like gunicorn
    application = app