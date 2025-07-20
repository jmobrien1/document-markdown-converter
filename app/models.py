# app/models.py
# Enhanced with freemium features and anonymous usage tracking

from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from . import db

class User(db.Model):
    """User model for storing user accounts."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    # Premium features
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    premium_expires = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)

    # Relationship to conversions
    conversions = db.relationship('Conversion', backref='user', lazy='dynamic')

    # Flask-Login required properties and methods
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        # Hash password using pure bcrypt
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password):
        # Check password using pure bcrypt
        try:
            # Try to verify with pure bcrypt first
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
        except Exception:
            # Fallback for old Flask-Bcrypt hashes (if any)
            try:
                from flask_bcrypt import Bcrypt
                flask_bcrypt = Bcrypt()
                return flask_bcrypt.check_password_hash(self.password_hash, password)
            except ImportError:
                return False

    def get_daily_conversions(self):
        """Get number of conversions today."""
        today = datetime.now(timezone.utc).date()
        return self.conversions.filter(
            db.func.date(Conversion.created_at) == today
        ).count()

    def can_convert(self):
        """Check if user can perform conversions (always True for logged-in users)."""
        return True

    def __repr__(self):
        return f'<User {self.email}>'


class Conversion(db.Model):
    """Model to track conversion history and usage."""
    __tablename__ = 'conversions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    session_id = db.Column(db.String(64), nullable=True)  # For anonymous users

    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    file_type = db.Column(db.String(10))

    # Conversion details
    conversion_type = db.Column(db.String(20), default='standard')  # 'standard' or 'pro'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'completed', 'failed'
    error_message = db.Column(db.Text, nullable=True)
    job_id = db.Column(db.String(64), nullable=True)

    # Timing
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    processing_time = db.Column(db.Float, nullable=True)  # Seconds

    # Results
    markdown_length = db.Column(db.Integer, nullable=True)  # Character count

    @property
    def duration(self):
        """Calculate processing duration."""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    def __repr__(self):
        return f'<Conversion {self.original_filename} - {self.status}>'


class AnonymousUsage(db.Model):
    """Track anonymous user usage by session/IP."""
    __tablename__ = 'anonymous_usage'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)

    # Usage tracking
    conversions_today = db.Column(db.Integer, default=0)
    last_conversion = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @classmethod
    def get_or_create_session(cls, session_id, ip_address=None):
        """Get or create anonymous usage record."""
        usage = cls.query.filter_by(session_id=session_id).first()

        if not usage:
            usage = cls(session_id=session_id, ip_address=ip_address)
            db.session.add(usage)
            db.session.commit()

        return usage

    def can_convert(self, daily_limit=5):
        """Check if anonymous user can convert (rate limiting)."""
        today = datetime.now(timezone.utc).date()

        # Reset counter if it's a new day
        if (self.last_conversion and
            self.last_conversion.date() < today):
            self.conversions_today = 0
            db.session.commit()

        return self.conversions_today < daily_limit

    def increment_usage(self):
        """Increment usage counter."""
        today = datetime.now(timezone.utc).date()

        # Reset if new day
        if (self.last_conversion and
            self.last_conversion.date() < today):
            self.conversions_today = 0

        self.conversions_today += 1
        self.last_conversion = datetime.now(timezone.utc)
        db.session.commit()

    def __repr__(self):
        return f'<AnonymousUsage {self.session_id} - {self.conversions_today}/day>'