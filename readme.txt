📝 mdraft
A sleek, modern Flask web application that converts PDF and DOCX files to Markdown format using Microsoft's markitdown library.
Transform your documents into clean, readable Markdown with mdraft's intuitive interface.
✨ Features
	•	🚀 Fast Conversion: Powered by Microsoft's markitdown for reliable document processing
	•	📱 Modern UI: Responsive design with drag-and-drop support
	•	📋 Copy & Share: One-click copying to clipboard
	•	💾 Download Ready: Export as .ml (Markdown Language) files
	•	🔒 Secure: Automatic file cleanup and validation
	•	⚡ Real-time: Instant feedback and progress indicators
🎯 Supported Formats
	•	PDF documents (.pdf)
	•	Microsoft Word documents (.docx)
🚀 Quick Start
Prerequisites
	•	Python 3.7+
	•	pip package manager
Installation

bash
# Clone or download mdraft
git clone https://github.com/YOUR_USERNAME/mdraft.git
cd mdraft

# Install dependencies
pip install flask markitdown

# Run mdraft
python app.py
Visit http://localhost:5000 and start converting!
🎮 How to Use mdraft
1. Upload Your Document
	•	Drag & drop a PDF or DOCX file onto the upload area
	•	Or click to browse and select your file
	•	Maximum file size: 16MB
2. Convert with mdraft
	•	Click the "Convert with mdraft" button
	•	Watch the real-time progress indicator
	•	Wait for processing to complete
3. Get Your Markdown
	•	View the converted Markdown in the preview area
	•	Copy to clipboard with one click
	•	Download as .ml file for later use
📁 Project Structure

mdraft/
├── app.py                 # Main Flask application
├── templates/
│   └── index.html        # Modern frontend interface
├── uploads/              # Temporary storage (auto-created)
├── README.md            # Documentation
└── requirements.txt     # Python dependencies
⚙️ Configuration
File Size Limits

python
# In app.py - adjust maximum file size
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB
Adding File Types

python
# In app.py - extend supported formats
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'html'}
Custom Port

python
# In app.py - change default port
app.run(debug=True, host='0.0.0.0', port=8080)
🔧 Development
Local Development

bash
# Enable debug mode (default)
python app.py

# Production mode
FLASK_ENV=production python app.py
Requirements File

bash
# Generate requirements.txt
pip freeze > requirements.txt

# Install from requirements
pip install -r requirements.txt
🛠️ Troubleshooting
Common Issues
❌ "markitdown not found"

bash
pip install markitdown
❌ File upload fails
	•	Check file size (max 16MB)
	•	Verify file extension (.pdf or .docx)
	•	Ensure file isn't corrupted
❌ Conversion errors
	•	Try a different document
	•	Check if file is password-protected
	•	Verify markitdown installation: markitdown --help
❌ Port already in use

bash
# Change port in app.py
app.run(debug=True, port=5001)
Debug Mode

python
# Enable detailed error messages
app.run(debug=True)

# Disable for production
app.run(debug=False)
🔒 Security Features
	•	File Validation: Only PDF and DOCX files accepted
	•	Size Limits: Prevents large file uploads
	•	Automatic Cleanup: Temporary files are automatically deleted
	•	Secure Filenames: Protection against path traversal attacks
	•	Session Isolation: Unique file handling per user session
📊 Sample Conversion
Input: report.docx

# Quarterly Report

This is our **Q3 performance** summary.

## Key Metrics
- Revenue: $1.2M
- Growth: 15%
- Customers: 1,500

Visit our [website](https://company.com) for more details.
Output: mdraft_output.ml

markdown
# Quarterly Report

This is our **Q3 performance** summary.

## Key Metrics
- Revenue: $1.2M
- Growth: 15%
- Customers: 1,500

Visit our [website](https://company.com) for more details.
🌐 Deployment
Local Deployment

bash
python app.py
Production Deployment

bash
# Using Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Using Docker
docker build -t mdraft .
docker run -p 5000:5000 mdraft
📦 Dependencies
	•	Flask - Web framework
	•	markitdown - Microsoft's document conversion library
	•	Werkzeug - WSGI utilities
🤝 Contributing
	1	Fork the mdraft repository
	2	Create a feature branch: git checkout -b feature/amazing-feature
	3	Commit your changes: git commit -m 'Add amazing feature'
	4	Push to the branch: git push origin feature/amazing-feature
	5	Open a Pull Request
📄 License
mdraft is open source software licensed under the MIT License.
🆘 Support
Need help with mdraft?
	1	Check the troubleshooting section
	2	Verify all dependencies are installed
	3	Test markitdown directly: markitdown --help
	4	Open an issue on GitHub
🎉 Acknowledgments
	•	Microsoft for the excellent markitdown library
	•	Flask community for the robust web framework
	•	Contributors who help make mdraft better

Made with ❤️ for the developer community
Transform documents effortlessly with mdraft
