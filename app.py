import os
import subprocess
import tempfile
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
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(email):
    """Create a new user account"""
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (email) VALUES (?)', (email,))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # User already exists

def get_daily_usage(user_id=None, session_id=None):
    """Get today's usage count for user or session"""
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

def increment_usage(user_id=None, session_id=None):
    """Increment today's usage count"""
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    today = datetime.now().date()
    
    if user_id:
        cursor.execute('''
            INSERT INTO daily_usage (user_id, date, conversions_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET
            conversions_count = conversions_count + 1
        ''', (user_id, today))
    else:
        cursor.execute('''
            INSERT INTO daily_usage (session_id, date, conversions_count)
            VALUES (?, ?, 1)
            ON CONFLICT(session_id, date) DO UPDATE SET
            conversions_count = conversions_count + 1
        ''', (session_id, today))
    
    conn.commit()
    conn.close()

def log_conversion(user_id, session_id, filename, file_type, file_size, status):
    """Log conversion attempt"""
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO conversions (user_id, session_id, filename, file_type, file_size, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, session_id, filename, file_type, file_size, status))
    conn.commit()
    conn.close()

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
    session_id = session.get('session_id', str(uuid.uuid4()))
    session['session_id'] = session_id
    
    user_id = session.get('user_id')
    
    if user_id:
        # Logged in user
        user = get_user_by_email(session.get('user_email'))
        usage = get_daily_usage(user_id=user_id)
        return jsonify({
            'logged_in': True,
            'user': {'email': user[1], 'plan': user[3]},
            'daily_usage': usage,
            'daily_limit': 'unlimited',
            'remaining': 'unlimited'
        })
    else:
        # Anonymous user
        usage = get_daily_usage(session_id=session_id)
        return jsonify({
            'logged_in': False,
            'daily_usage': usage,
            'daily_limit': 5,
            'remaining': max(0, 5 - usage)
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

def convert_to_markdown(file_path):
    """Convert file to markdown using markitdown CLI"""
    try:
        # Run markitdown command with timeout
        result = subprocess.run(
            ['markitdown', file_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=120  # 2 minute timeout
        )
        return result.stdout, None
    except subprocess.TimeoutExpired:
        return None, "Conversion timed out. Please try with a smaller file or simpler format."
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
    """Handle file upload and conversion with usage tracking"""
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
        # Generate unique filename to avoid conflicts
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file_size = len(file.read())
        file.seek(0)  # Reset file pointer
        
        # Save uploaded file
        file.save(file_path)
        
        # Get file type for logging
        file_type = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
        
        # Convert to markdown
        markdown_content, error = convert_to_markdown(file_path)
        
        # Clean up uploaded file
        os.remove(file_path)
        
        if error:
            # Log failed conversion
            log_conversion(user_id, session_id, filename, file_type, file_size, 'failed')
            return jsonify({'error': error}), 500
        
        # Log successful conversion and increment usage
        log_conversion(user_id, session_id, filename, file_type, file_size, 'success')
        increment_usage(user_id, session_id)
        
        # Store markdown content in session or temporary file for download
        download_id = str(uuid.uuid4())
        temp_file_path = os.path.join(tempfile.gettempdir(), f"converted_{download_id}.ml")
        
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Get updated usage for response
        new_usage = get_daily_usage(user_id, session_id)
        remaining = 'unlimited' if user_id else max(0, 5 - new_usage)
        
        return jsonify({
            'success': True,
            'markdown': markdown_content,
            'download_id': download_id,
            'original_filename': filename,
            'usage_info': {
                'daily_usage': new_usage,
                'remaining': remaining,
                'is_logged_in': bool(user_id)
            }
        })
        
    except Exception as e:
        # Clean up file if it exists
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        
        # Log failed conversion
        if 'filename' in locals():
            log_conversion(user_id, session_id, filename, file_type, file_size, 'error')
        
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
