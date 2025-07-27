import pytest
from datetime import datetime, timedelta, timezone
from app.models import User, Subscription, Invoice
from app import db

class TestSubscriptionModel:
    """Test cases for the Subscription model."""
    
    def test_subscription_creation(self, app):
        """Test basic subscription creation."""
        with app.app_context():
            user = User(email='test@example.com')
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
            
            assert subscription.id is not None
            assert subscription.user_id == user.id
            assert subscription.stripe_subscription_id == 'sub_test123'
            assert subscription.status == 'active'
            assert subscription.tier == 'pro'
    
    def test_subscription_status_validation(self, app):
        """Test that subscription status only accepts valid values."""
        with app.app_context():
            user = User(email='status@example.com')
            db.session.add(user)
            db.session.commit()
            
            valid_statuses = ['active', 'past_due', 'canceled', 'incomplete', 'trialing']
            
            for status in valid_statuses:
                subscription = Subscription(
                    user_id=user.id,
                    stripe_subscription_id=f'sub_{status}_test',
                    stripe_customer_id='cus_test123',
                    status=status,
                    tier='starter',
                    current_period_start=datetime.now(timezone.utc),
                    current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
                )
                db.session.add(subscription)
                db.session.commit()
                
                assert subscription.status == status
    
    def test_subscription_tier_validation(self, app):
        """Test that subscription tier only accepts valid values."""
        with app.app_context():
            user = User(email='tier@example.com')
            db.session.add(user)
            db.session.commit()
            
            valid_tiers = ['starter', 'pro', 'enterprise']
            
            for tier in valid_tiers:
                subscription = Subscription(
                    user_id=user.id,
                    stripe_subscription_id=f'sub_{tier}_test',
                    stripe_customer_id='cus_test123',
                    status='active',
                    tier=tier,
                    current_period_start=datetime.now(timezone.utc),
                    current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
                )
                db.session.add(subscription)
                db.session.commit()
                
                assert subscription.tier == tier
    
    def test_subscription_relationships(self, app):
        """Test relationships between Subscription and other models."""
        with app.app_context():
            user = User(email='relationship@example.com')
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_rel_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            # Test user relationship
            assert subscription.user.id == user.id
            assert user.subscriptions.count() == 1
            assert user.subscriptions.first().id == subscription.id
    
    def test_subscription_methods(self, app):
        """Test subscription utility methods."""
        with app.app_context():
            user = User(email='methods@example.com')
            db.session.add(user)
            db.session.commit()
            
            now = datetime.now(timezone.utc)
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_methods_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=now,
                current_period_end=now + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            assert subscription.is_active() == True
            assert subscription.is_trialing() == False
            assert subscription.days_until_renewal() > 0
    
    def test_trial_subscription(self, app):
        """Test trial subscription functionality."""
        with app.app_context():
            user = User(email='trial@example.com')
            db.session.add(user)
            db.session.commit()
            
            now = datetime.now(timezone.utc)
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_trial_test',
                stripe_customer_id='cus_test123',
                status='trialing',
                tier='pro',
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                trial_end=now + timedelta(days=7)
            )
            db.session.add(subscription)
            db.session.commit()
            
            assert subscription.is_trialing() == True
            assert subscription.trial_days_remaining() > 0
    
    def test_subscription_with_invoices(self, app):
        """Test subscription with associated invoices."""
        with app.app_context():
            user = User(email='invoices@example.com')
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_invoices_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            # Create invoices
            invoice1 = Invoice(
                subscription_id=subscription.id,
                stripe_invoice_id='inv_test1',
                amount=2900,  # $29.00
                currency='usd',
                status='paid',
                paid_at=datetime.now(timezone.utc)
            )
            invoice2 = Invoice(
                subscription_id=subscription.id,
                stripe_invoice_id='inv_test2',
                amount=2900,
                currency='usd',
                status='open'
            )
            db.session.add_all([invoice1, invoice2])
            db.session.commit()
            
            assert subscription.invoices.count() == 2
            assert subscription.paid_invoices().count() == 1
            assert subscription.total_paid() == 2900

class TestInvoiceModel:
    """Test cases for the Invoice model."""
    
    def test_invoice_creation(self, app):
        """Test basic invoice creation."""
        with app.app_context():
            user = User(email='invoice@example.com')
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_invoice_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            invoice = Invoice(
                subscription_id=subscription.id,
                stripe_invoice_id='inv_test123',
                amount=2900,
                currency='usd',
                status='paid',
                paid_at=datetime.now(timezone.utc)
            )
            db.session.add(invoice)
            db.session.commit()
            
            assert invoice.id is not None
            assert invoice.subscription_id == subscription.id
            assert invoice.amount == 2900
            assert invoice.currency == 'usd'
            assert invoice.status == 'paid'
    
    def test_invoice_status_validation(self, app):
        """Test that invoice status only accepts valid values."""
        with app.app_context():
            user = User(email='status@example.com')
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_status_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            valid_statuses = ['paid', 'open', 'void', 'draft', 'uncollectible']
            
            for status in valid_statuses:
                invoice = Invoice(
                    subscription_id=subscription.id,
                    stripe_invoice_id=f'inv_{status}_test',
                    amount=2900,
                    currency='usd',
                    status=status
                )
                db.session.add(invoice)
                db.session.commit()
                
                assert invoice.status == status
    
    def test_invoice_relationships(self, app):
        """Test relationships between Invoice and Subscription."""
        with app.app_context():
            user = User(email='rel@example.com')
            db.session.add(user)
            db.session.commit()
            
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id='sub_rel_test',
                stripe_customer_id='cus_test123',
                status='active',
                tier='pro',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.session.add(subscription)
            db.session.commit()
            
            invoice = Invoice(
                subscription_id=subscription.id,
                stripe_invoice_id='inv_rel_test',
                amount=2900,
                currency='usd',
                status='paid'
            )
            db.session.add(invoice)
            db.session.commit()
            
            assert invoice.subscription.id == subscription.id
            assert subscription.invoices.count() == 1
            assert subscription.invoices.first().id == invoice.id 