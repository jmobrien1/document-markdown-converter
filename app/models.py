# app/models.py
# Enhanced with freemium features, subscription management, and anonymous usage tracking

from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from . import db

def check_column_exists(table_name, column_name):
    """Check if a column exists in the database."""
    try:
        from sqlalchemy import text
        result = db.session.execute(
            text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = :table_name AND column_name = :column_name
            """),
            {'table_name': table_name, 'column_name': column_name}
        ).fetchone()
        return result is not None
    except Exception:
        # If we can't check, assume it doesn't exist
        return False

class User(db.Model):
    """User model for storing user accounts."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    # Premium features (legacy - maintained for backward compatibility)
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    premium_expires = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)
    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
    
    # New subscription management fields
    subscription_status = db.Column(db.String(50), default='trial')  # trial, active, past_due, canceled, incomplete
    current_tier = db.Column(db.String(50), default='free')  # free, starter, pro, enterprise
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    last_payment_date = db.Column(db.DateTime, nullable=True)
    next_payment_date = db.Column(db.DateTime, nullable=True)
    
    # Trial features (enhanced for reverse trial logic)
    trial_start_date = db.Column(db.DateTime, nullable=True, info={'optional': True})
    trial_end_date = db.Column(db.DateTime, nullable=True, info={'optional': True})
    on_trial = db.Column(db.Boolean, default=True, info={'optional': True})
    
    # Usage tracking (optional - will be added by migration)
    pro_pages_processed_current_month = db.Column(db.Integer, default=0, info={'optional': True})

    # Relationship to conversions
    conversions = db.relationship('Conversion', backref='user', lazy='dynamic')
    
    @classmethod
    def get_user_safely(cls, user_id):
        """Get user safely, handling missing trial columns."""
        try:
            # Try to get user with all columns first
            return cls.query.get(user_id)
        except Exception as e:
            if 'trial_start_date' in str(e) or 'trial_end_date' in str(e) or 'on_trial' in str(e):
                # Rollback the failed transaction first
                db.session.rollback()
                
                # If trial columns don't exist, query only the core columns
                from sqlalchemy import text
                try:
                    result = db.session.execute(
                        text("""
                            SELECT id, email, password_hash, created_at, is_active, 
                                   is_premium, is_admin, premium_expires, 
                                   stripe_customer_id, stripe_subscription_id, api_key
                            FROM users WHERE id = :user_id
                        """),
                        {'user_id': user_id}
                    ).fetchone()
                    
                    if result:
                        # Create a user object with the available data
                        user = cls()
                        user.id = result.id
                        user.email = result.email
                        user.password_hash = result.password_hash
                        user.created_at = result.created_at
                        user.is_active = result.is_active
                        user.is_premium = result.is_premium
                        user.is_admin = result.is_admin
                        user.premium_expires = result.premium_expires
                        user.stripe_customer_id = result.stripe_customer_id
                        user.stripe_subscription_id = result.stripe_subscription_id
                        user.api_key = result.api_key
                        return user
                except Exception as fallback_error:
                    # If even the fallback fails, rollback again and try a simpler approach
                    db.session.rollback()
                    print(f"Fallback query failed: {fallback_error}")
                    raise e  # Re-raise the original error
            raise e

    # Flask-Login required properties and methods
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        # Return the database column value if it exists, otherwise True
        try:
            return self._is_active if hasattr(self, '_is_active') else True
        except:
            return True
    
    @is_active.setter
    def is_active(self, value):
        # Set the database column value
        self._is_active = value

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
    
    @property
    def has_pro_access(self):
        """Check if user has Pro access (either premium or on trial)."""
        if self.is_premium:
            return True
        
        # Check if user is on trial and trial hasn't expired
        # Handle case where trial fields don't exist yet (graceful degradation)
        try:
            # Check if trial columns exist before accessing them
            if (check_column_exists('users', 'on_trial') and 
                check_column_exists('users', 'trial_end_date') and
                hasattr(self, 'on_trial') and self.on_trial and 
                hasattr(self, 'trial_end_date') and self.trial_end_date):
                return datetime.now(timezone.utc) < self.trial_end_date
        except:
            pass
        
        return False
    
    @property
    def trial_days_remaining(self):
        """Get the number of days remaining in the trial."""
        try:
            # Check if trial columns exist before accessing them
            if not (check_column_exists('users', 'on_trial') and 
                   check_column_exists('users', 'trial_end_date')):
                return 0
                
            if not hasattr(self, 'on_trial') or not self.on_trial or not hasattr(self, 'trial_end_date') or not self.trial_end_date:
                return 0
            
            remaining = self.trial_end_date - datetime.now(timezone.utc)
            return max(0, remaining.days)
        except:
            return 0

    def generate_api_key(self):
        import secrets
        token = secrets.token_urlsafe(48)[:64]
        self.api_key = token
        db.session.commit()
        return token

    def revoke_api_key(self):
        """Revoke the current API key by setting it to None."""
        self.api_key = None
        db.session.commit()

    # New subscription-related methods
    def is_in_trial(self):
        """Check if user is currently in trial period."""
        if not self.trial_end_date:
            return False
        # Ensure both datetimes are timezone-aware
        now = datetime.now(timezone.utc)
        trial_end = self.trial_end_date
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        return now < trial_end
    
    def trial_days_remaining(self):
        """Get the number of days remaining in the trial."""
        if not self.trial_end_date:
            return 0
        # Ensure both datetimes are timezone-aware
        now = datetime.now(timezone.utc)
        trial_end = self.trial_end_date
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        remaining = trial_end - now
        return max(0, remaining.days)
    
    def has_active_subscription(self):
        """Check if user has an active subscription."""
        return self.subscription_status in ['active', 'trialing']
    
    def can_access_pro_features(self):
        """Check if user can access Pro features."""
        return (self.has_active_subscription() or 
                self.is_premium or 
                (self.is_in_trial() and self.current_tier in ['pro', 'enterprise']))
    
    def start_trial(self, tier='pro', days=7):
        """Start a trial period for the user."""
        now = datetime.now(timezone.utc)
        self.trial_start_date = now
        self.trial_end_date = now + timedelta(days=days)
        self.subscription_status = 'trial'
        self.current_tier = tier
        self.on_trial = True
        db.session.commit()
    
    def expire_trial(self):
        """Expire the trial and downgrade user."""
        self.subscription_status = 'canceled'
        self.current_tier = 'free'
        self.on_trial = False
        self.trial_end_date = datetime.now(timezone.utc)
        db.session.commit()
    
    def setup_premium_user(self):
        """Setup subscription fields for existing premium users."""
        if self.is_premium and self.subscription_status == 'trial':
            self.subscription_status = 'active'
            self.current_tier = 'pro'
            self.subscription_start_date = self.created_at
            db.session.commit()

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
    pages_processed = db.Column(db.Integer, nullable=True, info={'optional': True})  # Number of pages processed (for Pro conversions)

    @property
    def duration(self):
        """Calculate processing duration."""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    def __repr__(self):
        return f'<Conversion {self.original_filename} - {self.status}>'
    
    @classmethod
    def get_conversion_safely(cls, conversion_id):
        """Get conversion safely, handling missing pages_processed column."""
        try:
            # Try to get conversion with all columns first
            return cls.query.get(conversion_id)
        except Exception as e:
            if 'pages_processed' in str(e):
                # Rollback the failed transaction first
                db.session.rollback()
                
                # If pages_processed column doesn't exist, query only the core columns
                from sqlalchemy import text
                try:
                    result = db.session.execute(
                        text("""
                            SELECT id, user_id, session_id, original_filename, file_size, file_type,
                                   conversion_type, status, error_message, job_id, created_at, 
                                   completed_at, processing_time, markdown_length
                            FROM conversions WHERE id = :conversion_id
                        """),
                        {'conversion_id': conversion_id}
                    ).fetchone()
                    
                    if result:
                        # Create a conversion object with the available data
                        conversion = cls()
                        conversion.id = result.id
                        conversion.user_id = result.user_id
                        conversion.session_id = result.session_id
                        conversion.original_filename = result.original_filename
                        conversion.file_size = result.file_size
                        conversion.file_type = result.file_type
                        conversion.conversion_type = result.conversion_type
                        conversion.status = result.status
                        conversion.error_message = result.error_message
                        conversion.job_id = result.job_id
                        conversion.created_at = result.created_at
                        conversion.completed_at = result.completed_at
                        conversion.processing_time = result.processing_time
                        conversion.markdown_length = result.markdown_length
                        return conversion
                except Exception as fallback_error:
                    # If even the fallback fails, rollback again
                    db.session.rollback()
                    print(f"Fallback conversion query failed: {fallback_error}")
                    raise e  # Re-raise the original error
            raise e


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


class Subscription(db.Model):
    """Model to track Stripe subscriptions."""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    stripe_customer_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # active, past_due, canceled, incomplete, trialing
    tier = db.Column(db.String(50), nullable=False)  # starter, pro, enterprise
    current_period_start = db.Column(db.DateTime, nullable=False)
    current_period_end = db.Column(db.DateTime, nullable=False)
    trial_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = db.relationship('User', backref=db.backref('subscriptions', lazy='dynamic'))
    invoices = db.relationship('Invoice', backref='subscription', lazy='dynamic')
    
    def is_active(self):
        """Check if subscription is active."""
        return self.status in ['active', 'trialing']
    
    def is_trialing(self):
        """Check if subscription is in trial period."""
        return self.status == 'trialing'
    
    def trial_days_remaining(self):
        """Get days remaining in trial."""
        if not self.trial_end:
            return 0
        # Ensure both datetimes are timezone-aware
        now = datetime.now(timezone.utc)
        trial_end = self.trial_end
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        remaining = trial_end - now
        return max(0, remaining.days)
    
    def days_until_renewal(self):
        """Get days until next renewal."""
        # Ensure both datetimes are timezone-aware
        now = datetime.now(timezone.utc)
        period_end = self.current_period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        remaining = period_end - now
        return max(0, remaining.days)
    
    def paid_invoices(self):
        """Get all paid invoices for this subscription."""
        return self.invoices.filter_by(status='paid')
    
    def total_paid(self):
        """Get total amount paid for this subscription."""
        return sum(invoice.amount for invoice in self.paid_invoices())
    
    def __repr__(self):
        return f'<Subscription {self.stripe_subscription_id} - {self.status}>'


class Invoice(db.Model):
    """Model to track Stripe invoices."""
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    stripe_invoice_id = db.Column(db.String(255), unique=True, nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # Amount in cents
    currency = db.Column(db.String(3), default='usd')
    status = db.Column(db.String(50), nullable=False)  # paid, open, void, draft, uncollectible
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    paid_at = db.Column(db.DateTime, nullable=True)
    
    def is_paid(self):
        """Check if invoice is paid."""
        return self.status == 'paid'
    
    def amount_in_dollars(self):
        """Get amount in dollars."""
        return self.amount / 100
    
    def __repr__(self):
        return f'<Invoice {self.stripe_invoice_id} - {self.status}>'