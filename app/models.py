# app/models.py
# Enhanced with freemium features, subscription management, and anonymous usage tracking

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
    
    # Team relationships
    owned_teams = db.relationship('Team', backref='owner', lazy='dynamic', foreign_keys='Team.owner_id')
    team_memberships = db.relationship('TeamMember', backref='user', lazy='dynamic')
    
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
        
        # Normal case with relationship loaded
        return self.conversions.filter(
            db.func.date(Conversion.created_at) == today
        ).count()

    def can_convert(self):
        """Check if user can perform a conversion."""
        return self.is_active and (self.has_pro_access or self.get_daily_conversions() < 5)

    @property
    def has_pro_access(self):
        """Check if user has access to Pro features."""
        try:
            # Check if user is on trial and trial hasn't expired
            if self.on_trial and self.trial_end_date:
                # Ensure timezone-aware comparison
                current_time = datetime.now(timezone.utc)
                trial_end = self.trial_end_date
                if trial_end.tzinfo is None:
                    # If trial_end_date is timezone-naive, assume UTC
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                if current_time < trial_end:
                    return True
            
            # Check if user has active subscription
            if self.is_premium or self.current_tier in ['pro', 'enterprise']:
                return True
            
            return False
        except Exception as e:
            # If any error occurs (e.g., missing columns), default to False
            print(f"Error in has_pro_access: {e}")
            return False

    @property
    def trial_days_remaining(self):
        """Calculate remaining trial days."""
        try:
            if not self.on_trial or not self.trial_end_date:
                return 0
            
            # Ensure timezone-aware comparison
            current_time = datetime.now(timezone.utc)
            trial_end = self.trial_end_date
            if trial_end.tzinfo is None:
                # If trial_end_date is timezone-naive, assume UTC
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            
            remaining = trial_end - current_time
            return max(0, remaining.days)
        except Exception as e:
            print(f"Error in trial_days_remaining: {e}")
            return 0

    def generate_api_key(self):
        """Generate a new API key for the user."""
        import secrets
        self.api_key = secrets.token_hex(32)
        return self.api_key

    def revoke_api_key(self):
        """Revoke the user's API key."""
        self.api_key = None

    def is_in_trial(self):
        """Check if user is currently in trial period."""
        try:
            if not self.on_trial or not self.trial_end_date:
                return False
            return datetime.now(timezone.utc) < self.trial_end_date
        except Exception:
            return False

    def has_active_subscription(self):
        """Check if user has an active subscription."""
        return self.is_premium or self.current_tier in ['pro', 'enterprise']

    def can_access_pro_features(self):
        """Check if user can access Pro features."""
        return self.has_pro_access

    def start_trial(self, tier='pro', days=7):
        """Start a trial period for the user."""
        self.on_trial = True
        self.trial_start_date = datetime.now(timezone.utc)
        self.trial_end_date = self.trial_start_date + timedelta(days=days)
        self.current_tier = tier

    def expire_trial(self):
        """Expire the user's trial."""
        self.on_trial = False
        self.trial_end_date = None

    def setup_premium_user(self):
        """Set up a user as premium."""
        self.is_premium = True
        self.current_tier = 'pro'
        self.on_trial = False

    def __repr__(self):
        return f'<User {self.email}>'


class Team(db.Model):
    """Team model for enterprise team accounts."""
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    members = db.relationship('TeamMember', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    
    def add_member(self, user, role='member'):
        """Add a user to the team with a specific role."""
        membership = TeamMember(user_id=user.id, team_id=self.id, role=role)
        db.session.add(membership)
        return membership
    
    def remove_member(self, user):
        """Remove a user from the team."""
        membership = TeamMember.query.filter_by(user_id=user.id, team_id=self.id).first()
        if membership:
            db.session.delete(membership)
            return True
        return False
    
    def is_admin(self, user):
        """Check if a user is an admin of this team."""
        membership = TeamMember.query.filter_by(user_id=user.id, team_id=self.id).first()
        return membership and membership.role == 'admin'
    
    def is_member(self, user):
        """Check if a user is a member of this team."""
        membership = TeamMember.query.filter_by(user_id=user.id, team_id=self.id).first()
        return membership is not None
    
    def get_member_role(self, user):
        """Get the role of a user in this team."""
        membership = TeamMember.query.filter_by(user_id=user.id, team_id=self.id).first()
        return membership.role if membership else None
    
    def __repr__(self):
        return f'<Team {self.name}>'


class TeamMember(db.Model):
    """Association table for team memberships."""
    __tablename__ = 'team_members'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='member')  # 'admin', 'member'
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Unique constraint to prevent duplicate memberships
    __table_args__ = (db.UniqueConstraint('user_id', 'team_id', name='uq_user_team'),)
    
    def __repr__(self):
        return f'<TeamMember {self.user_id} in {self.team_id} as {self.role}>'


class Conversion(db.Model):
    """Model to track conversion history and usage."""
    __tablename__ = 'conversions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    session_id = db.Column(db.String(64), nullable=True)  # For anonymous users

    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    gcs_path = db.Column(db.String(500), nullable=True)  # Path to original file in GCS

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
    structured_data = db.Column(db.JSON, nullable=True)  # Extracted structured data from AI analysis

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


class Batch(db.Model):
    """Model to track batch upload jobs."""
    __tablename__ = 'batches'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    batch_id = db.Column(db.String(64), unique=True, nullable=False)  # UUID for external reference
    status = db.Column(db.String(50), default='queued')  # queued, processing, completed, failed
    total_files = db.Column(db.Integer, default=0)
    processed_files = db.Column(db.Integer, default=0)
    failed_files = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('batches', lazy='dynamic'))
    conversion_jobs = db.relationship('ConversionJob', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    
    def progress_percentage(self):
        """Calculate progress percentage."""
        if self.total_files == 0:
            return 0
        return int((self.processed_files + self.failed_files) / self.total_files * 100)
    
    def is_completed(self):
        """Check if batch is completed."""
        return self.status in ['completed', 'failed']
    
    def update_progress(self):
        """Update progress based on conversion jobs."""
        completed = self.conversion_jobs.filter_by(status='completed').count()
        failed = self.conversion_jobs.filter_by(status='failed').count()
        self.processed_files = completed
        self.failed_files = failed
        
        if completed + failed == self.total_files:
            self.status = 'completed' if failed == 0 else 'failed'
            self.completed_at = datetime.now(timezone.utc)
        
        db.session.commit()
    
    def __repr__(self):
        return f'<Batch {self.batch_id} - {self.status}>'


class ConversionJob(db.Model):
    """Model to track individual conversion jobs within a batch."""
    __tablename__ = 'conversion_jobs'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    file_type = db.Column(db.String(10))
    
    # Job details
    status = db.Column(db.String(50), default='queued')  # queued, processing, completed, failed
    error_message = db.Column(db.Text, nullable=True)
    job_id = db.Column(db.String(64), nullable=True)  # Celery task ID
    
    # Timing
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    processing_time = db.Column(db.Float, nullable=True)  # Seconds
    
    # Results
    markdown_content = db.Column(db.Text, nullable=True)
    markdown_length = db.Column(db.Integer, nullable=True)  # Character count
    pages_processed = db.Column(db.Integer, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('conversion_jobs', lazy='dynamic'))
    
    def start_processing(self):
        """Mark job as started."""
        self.status = 'processing'
        self.started_at = datetime.now(timezone.utc)
        db.session.commit()
    
    def complete_success(self, markdown_content, pages_processed=None):
        """Mark job as completed successfully."""
        self.status = 'completed'
        self.completed_at = datetime.now(timezone.utc)
        self.markdown_content = markdown_content
        self.markdown_length = len(markdown_content) if markdown_content else 0
        self.pages_processed = pages_processed
        
        if self.started_at:
            # Ensure both datetimes are timezone-aware
            completed_at = self.completed_at
            started_at = self.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            self.processing_time = (completed_at - started_at).total_seconds()
        
        db.session.commit()
    
    def complete_failure(self, error_message):
        """Mark job as failed."""
        self.status = 'failed'
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
        
        if self.started_at:
            # Ensure both datetimes are timezone-aware
            completed_at = self.completed_at
            started_at = self.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            self.processing_time = (completed_at - started_at).total_seconds()
        
        db.session.commit()
    
    def __repr__(self):
        return f'<ConversionJob {self.original_filename} - {self.status}>'


class Summary(db.Model):
    """Model for storing generated summaries."""
    __tablename__ = 'summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    conversion_id = db.Column(db.Integer, db.ForeignKey('conversions.id'), nullable=False)
    length_type = db.Column(db.String(20), nullable=False)  # 'sentence', 'paragraph', 'bullets'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    conversion = db.relationship('Conversion', backref=db.backref('summaries', lazy=True))
    
    def __repr__(self):
        return f'<Summary {self.id}: {self.length_type} for conversion {self.conversion_id}>'


class RAGChunk(db.Model):
    """Model for storing document chunks for RAG."""
    __tablename__ = 'rag_chunks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey('conversions.id'), nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    chunk_text = db.Column(db.Text, nullable=False)
    embedding = db.Column(db.JSON, nullable=True)  # JSON for easier debugging and consistency
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    conversion = db.relationship('Conversion', backref=db.backref('rag_chunks', lazy=True))

    def __repr__(self):
        return f'<RAGChunk {self.id}: doc={self.document_id}, idx={self.chunk_index}>'


class RAGQuery(db.Model):
    """Model for storing RAG queries and answers."""
    __tablename__ = 'rag_queries'

    id = db.Column(db.Integer, primary_key=True)
    query_text = db.Column(db.Text, nullable=False)  # Changed from question
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Added user_id
    results_count = db.Column(db.Integer, nullable=True)  # Added results_count
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('rag_queries', lazy=True))

    def __repr__(self):
        return f'<RAGQuery {self.id} by user {self.user_id}>'