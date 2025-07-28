# tests/test_security.py
# Security tests for file upload validation and virus scanning

import pytest
import tempfile
import os
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from app.main.routes import validate_file_signature, validate_file_content
from app.tasks import scan_file_for_viruses
from app import create_app

class TestFileSignatureValidation:
    """Test file signature (magic number) validation."""
    
    def test_valid_pdf_signature(self):
        """Test that valid PDF files pass signature validation."""
        # Create a mock PDF file with correct signature
        pdf_content = b'%PDF-1.4\n%Test PDF content'
        file_stream = BytesIO(pdf_content)
        
        is_valid, error = validate_file_signature(file_stream, 'test.pdf')
        assert is_valid
        assert error is None
    
    def test_invalid_pdf_signature(self):
        """Test that files with wrong signature are rejected."""
        # Create a file with PDF extension but wrong signature
        fake_content = b'This is not a PDF file'
        file_stream = BytesIO(fake_content)
        
        is_valid, error = validate_file_signature(file_stream, 'fake.pdf')
        assert not is_valid
        assert 'File signature does not match extension' in error
    
    def test_valid_docx_signature(self):
        """Test that valid DOCX files pass signature validation."""
        # Create a mock DOCX file with ZIP signature
        docx_content = b'PK\x03\x04\x14\x00\x00\x00\x08\x00'
        file_stream = BytesIO(docx_content)
        
        is_valid, error = validate_file_signature(file_stream, 'test.docx')
        assert is_valid
        assert error is None
    
    def test_valid_png_signature(self):
        """Test that valid PNG files pass signature validation."""
        # Create a mock PNG file with correct signature
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0D'
        file_stream = BytesIO(png_content)
        
        is_valid, error = validate_file_signature(file_stream, 'test.png')
        assert is_valid
        assert error is None
    
    def test_unsupported_file_type(self):
        """Test that unsupported file types are rejected."""
        file_stream = BytesIO(b'Some content')
        
        is_valid, error = validate_file_signature(file_stream, 'test.exe')
        assert not is_valid
        assert 'Unsupported file type' in error
    
    def test_no_extension(self):
        """Test that files without extensions are rejected."""
        file_stream = BytesIO(b'Some content')
        
        is_valid, error = validate_file_signature(file_stream, 'testfile')
        assert not is_valid
        assert 'Unsupported file type' in error

class TestFileContentValidation:
    """Test file content validation for text-based files."""
    
    def test_valid_text_file(self):
        """Test that valid text files pass content validation."""
        text_content = b'This is a valid text file with UTF-8 content.'
        file_stream = BytesIO(text_content)
        
        is_valid, error = validate_file_content(file_stream, 'test.txt')
        assert is_valid
        assert error is None
    
    def test_valid_json_file(self):
        """Test that valid JSON files pass content validation."""
        json_content = b'{"key": "value", "number": 42}'
        file_stream = BytesIO(json_content)
        
        is_valid, error = validate_file_content(file_stream, 'test.json')
        assert is_valid
        assert error is None
    
    def test_invalid_json_file(self):
        """Test that invalid JSON files are rejected."""
        invalid_json = b'{"key": "value", "number": 42'  # Missing closing brace
        file_stream = BytesIO(invalid_json)
        
        is_valid, error = validate_file_content(file_stream, 'test.json')
        assert not is_valid
        assert 'Invalid JSON format' in error
    
    def test_binary_file_with_text_extension(self):
        """Test that binary files with text extensions are rejected."""
        # Use more binary-like content that will definitely fail UTF-8 decode
        binary_content = b'\xFF\xFE\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C\x0D\x0E\x0F'
        file_stream = BytesIO(binary_content)
        
        is_valid, error = validate_file_content(file_stream, 'fake.txt')
        assert not is_valid
        assert 'appears to be binary' in error
    
    def test_pdf_file_content_validation(self):
        """Test that PDF files are not subject to text content validation."""
        pdf_content = b'%PDF-1.4\n%Test PDF content'
        file_stream = BytesIO(pdf_content)
        
        is_valid, error = validate_file_content(file_stream, 'test.pdf')
        assert is_valid
        assert error is None

class TestVirusScanning:
    """Test virus scanning functionality."""
    
    @patch('app.tasks.shutil.which')
    @patch('app.tasks.subprocess.run')
    def test_clean_file_scan(self, mock_run, mock_which):
        """Test that clean files pass virus scanning."""
        # Create Flask app context
        app = create_app()
        
        with app.app_context():
            # Mock ClamAV availability
            mock_which.return_value = '/usr/bin/clamscan'
            
            # Mock successful scan
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "OK"
            mock_run.return_value = mock_result
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(b'Clean file content')
                temp_file.flush()
                
                is_clean, message = scan_file_for_viruses(temp_file.name)
                assert is_clean
                assert 'no threats detected' in message
    
    @patch('app.tasks.shutil.which')
    @patch('app.tasks.subprocess.run')
    def test_infected_file_scan(self, mock_run, mock_which):
        """Test that infected files are detected."""
        # Create Flask app context
        app = create_app()
        
        with app.app_context():
            # Mock ClamAV availability
            mock_which.return_value = '/usr/bin/clamscan'
            
            # Mock virus detection
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = "test.txt: Win.Test.EICAR_HDB-1 FOUND"
            mock_run.return_value = mock_result
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(b'Infected file content')
                temp_file.flush()
                
                is_clean, message = scan_file_for_viruses(temp_file.name)
                assert not is_clean
                assert 'Virus detected' in message
    
    @patch('app.tasks.shutil.which')
    def test_clamav_not_available(self, mock_which):
        """Test behavior when ClamAV is not available."""
        # Create Flask app context
        app = create_app()
        
        with app.app_context():
            # Mock ClamAV not available
            mock_which.return_value = None
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(b'File content')
                temp_file.flush()
                
                is_clean, message = scan_file_for_viruses(temp_file.name)
                assert is_clean  # Should pass when ClamAV not available
                assert 'ClamAV not available' in message
    
    @patch('app.tasks.shutil.which')
    @patch('app.tasks.subprocess.run')
    def test_scan_timeout(self, mock_run, mock_which):
        """Test that scan timeouts are handled properly."""
        # Create Flask app context
        app = create_app()
        
        with app.app_context():
            # Mock ClamAV availability
            mock_which.return_value = '/usr/bin/clamscan'
            
            # Mock timeout
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(['clamscan'], 30)
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(b'File content')
                temp_file.flush()
                
                is_clean, message = scan_file_for_viruses(temp_file.name)
                assert not is_clean
                assert 'timeout' in message.lower()
    
    @patch('app.tasks.shutil.which')
    @patch('app.tasks.subprocess.run')
    def test_scan_error(self, mock_run, mock_which):
        """Test that scan errors are handled properly."""
        # Create Flask app context
        app = create_app()
        
        with app.app_context():
            # Mock ClamAV availability
            mock_which.return_value = '/usr/bin/clamscan'
            
            # Mock scan error
            mock_result = MagicMock()
            mock_result.returncode = 2
            mock_result.stderr = "Permission denied"
            mock_run.return_value = mock_result
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(b'File content')
                temp_file.flush()
                
                is_clean, message = scan_file_for_viruses(temp_file.name)
                assert not is_clean
                assert 'Virus scan error' in message

class TestSecurityIntegration:
    """Integration tests for security features."""
    
    def test_complete_file_validation_workflow(self):
        """Test the complete file validation workflow."""
        # Test a valid PDF file
        pdf_content = b'%PDF-1.4\n%Test PDF content'
        file_stream = BytesIO(pdf_content)
        
        # Test signature validation
        is_valid_signature, signature_error = validate_file_signature(file_stream, 'test.pdf')
        assert is_valid_signature
        assert signature_error is None
        
        # Test content validation (should pass for PDFs)
        is_valid_content, content_error = validate_file_content(file_stream, 'test.pdf')
        assert is_valid_content
        assert content_error is None
    
    def test_malicious_file_detection(self):
        """Test detection of malicious files."""
        # Test file with wrong signature
        fake_content = b'This is not a PDF but has .pdf extension'
        file_stream = BytesIO(fake_content)
        
        is_valid_signature, signature_error = validate_file_signature(file_stream, 'malicious.pdf')
        assert not is_valid_signature
        assert 'File signature does not match extension' in signature_error
    
    def test_binary_file_masquerading_as_text(self):
        """Test detection of binary files with text extensions."""
        # Use more binary-like content that will definitely fail UTF-8 decode
        binary_content = b'\xFF\xFE\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C\x0D\x0E\x0F'
        file_stream = BytesIO(binary_content)
        
        is_valid_content, content_error = validate_file_content(file_stream, 'fake.txt')
        assert not is_valid_content
        assert 'appears to be binary' in content_error

if __name__ == '__main__':
    pytest.main([__file__]) 