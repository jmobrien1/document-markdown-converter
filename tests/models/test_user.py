import pytest
from datetime import datetime, timedelta, timezone
from app.models import User, Subscription
from app import db

class TestUserModel:
    """Test cases for the enhanced User model with subscription functionality."""
    
    def test_user_creation(self, app):
        """Test basic user creation with new subscription fields."""
        with app.app_context():
            user = User(
                email='test@example.com',
                subscription_status='trial',
                current_tier='free',
                trial_end_date=datetime.now(timezone.utc) + timedelta(days=7)
            )
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.subscription_status == 'trial'
            assert user.current_tier == 'free'
            assert user.trial_end_date is not None
    
    def test_subscription_status_enum(self, app):
        """Test that subscription_status only accepts valid values."""
        with app.app_context():
            valid_statuses = ['trial', 'active', 'past_due', 'canceled', 'incomplete']
            
            for status in valid_statuses:
                user = User(
                    email=f'test_{status}@example.com',
                    subscription_status=status,
                    current_tier='free'
                )
                db.session.add(user)
                db.session.commit()
                
                assert user.subscription_status == status
    
    def test_current_tier_enum(self, app):
        """Test that current_tier only accepts valid values."""
        with app.app_context():
            valid_tiers = ['free', 'starter', 'pro', 'enterprise']
            
            for tier in valid_tiers:
                user = User(
                    email=f'test_{tier}@example.com',
                    subscription_status='active',
                    current_tier=tier
                )
                db.session.add(user)
                db.session.commit()
                
                assert user.current_tier == tier
    
    def test_trial_logic(self, app):
        """Test trial-related functionality."""
        with app.app_context():
            # User starting trial
            trial_start = datetime.now(timezone.utc)
            trial_end = trial_start + timedelta(days=7)
            
            user = User(
                email='trial@example.com',
                subscription_status='trial',
                current_tier='free',
                trial_start_date=trial_start,
                trial_end_date=trial_end
            )
            db.session.add(user)
            db.session.commit()
            
            assert user.is_in_trial() == True
            assert user.trial_days_remaining() > 0
    
    def test_subscription_relationship(self, app):
        """Test relationship between User and Subscription models."""
        with app.app_context():
            user = User(
                email='subscription@example.com',
                subscription_status='active',
                current_tier='pro'
            )
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_test123',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            assert user.subscriptions.count() == 1
            assert user.subscriptions.first().tier == 'pro'
    
    def test_subscription_methods(self, app):
        """Test subscription-related methods."""
        with app.app_context():
            user = User(
                email='methods@example.com',
                subscription_status='active',
                current_tier='pro',
                subscription_start_date=datetime.now(timezone.utc),
                last_payment_date=datetime.now(timezone.utc),
                next_payment_date=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(user)
            db.session.commit()
            
            assert user.has_active_subscription() == True
            assert user.can_access_pro_features() == True
    
    def test_backward_compatibility(self, app):
        """Test that existing user fields still work."""
        with app.app_context():
            user = User(
                email='legacy@example.com',
                is_premium=True,
                premium_expires=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(user)
            db.session.commit()
            
            # Legacy fields should still work
            assert user.is_premium == True
            assert user.premium_expires is not None
            
            # Setup premium user subscription fields
            user.setup_premium_user()
            
            # New fields should be set for premium users
            assert user.subscription_status == 'active'  # Updated for premium users
            assert user.current_tier == 'pro'  # Updated for premium users 