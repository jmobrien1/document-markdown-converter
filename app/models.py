# app/models.py
# Enhanced with freemium features and anonymous usage tracking

from datetime import datetime, timedelta
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from . import db, bcrypt

class User(UserMixin, db.Model):
    """User model for storing user accounts."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Premium features
    is_premium = db.Column(db.Boolean, default=False)
    premium_expires = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)

    # Relationship to conversions
    conversions = db.relationship('Conversion', backref='user', lazy='dynamic')

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def verify_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def get_daily_conversions(self):
        """Get number of conversions today."""
        today = datetime.utcnow().date()
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

    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        today = datetime.utcnow().date()

        # Reset counter if it's a new day
        if (self.last_conversion and
            self.last_conversion.date() < today):
            self.conversions_today = 0
            db.session.commit()

        return self.conversions_today < daily_limit

    def increment_usage(self):
        """Increment usage counter."""
        today = datetime.utcnow().date()

        # Reset if new day
        if (self.last_conversion and
            self.last_conversion.date() < today):
            self.conversions_today = 0

        self.conversions_today += 1
        self.last_conversion = datetime.utcnow()
        db.session.commit()

    def __repr__(self):
        return f'<AnonymousUsage {self.session_id} - {self.conversions_today}/day>'