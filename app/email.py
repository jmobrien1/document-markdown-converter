# app/email.py
# Email notification functions for the application

from flask import current_app, url_for
from flask_mail import Message
from app import mail

def send_conversion_complete_email(user_email, filename):
    """
    Send an email notification to the user when their file conversion is complete.
    
    Args:
        user_email (str): The user's email address
        filename (str): The original filename that was converted
    """
    try:
        # Check if email is configured
        if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            current_app.logger.warning("❌ Email not configured - MAIL_USERNAME or MAIL_PASSWORD not set")
            return
            
        subject = 'Your mdraft Conversion is Complete!'
        
        # Create the email body
        body = f"""
Hello!

Your file "{filename}" has been successfully converted to Markdown format.

You can view and download your converted file by visiting your account dashboard:
{url_for('auth.account', _external=True)}

Thank you for using mdraft!

Best regards,
The mdraft Team
        """.strip()
        
        # Create and send the message
        msg = Message(
            subject=subject,
            recipients=[user_email],
            body=body
        )
        
        mail.send(msg)
        current_app.logger.info(f"✅ Email notification sent to {user_email} for file {filename}")
        
    except Exception as e:
        current_app.logger.error(f"❌ Failed to send email notification to {user_email}: {str(e)}")
        # Don't raise the exception - we don't want email failures to break the conversion process 