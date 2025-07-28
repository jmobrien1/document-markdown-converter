# app/auth/routes.py
# Enhanced with Stripe payment integration - NO MODULE-LEVEL STRIPE IMPORT

import re
from datetime import datetime, timedelta, timezone
from flask import render_template, redirect, request, url_for, flash, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from .. import db
from ..models import User, AnonymousUsage, Conversion



def is_valid_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Validation
        errors = []

        if not email:
            errors.append('Email is required')
        elif not is_valid_email(email):
            errors.append('Please enter a valid email address')

        if not password:
            errors.append('Password is required')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters long')

        # Check if user already exists
        if email and User.query.filter_by(email=email).first():
            errors.append('Email address already registered')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('signup.html')

        try:
            # Create new user with trial
            from datetime import datetime, timedelta, timezone
            
            user = User(email=email)
            user.password = password  # Use the User model's password setter
            
            # Set trial dates (14-day trial)
            user.trial_start_date = datetime.now(timezone.utc)
            user.trial_end_date = user.trial_start_date + timedelta(days=14)
            user.on_trial = True

            db.session.add(user)
            db.session.commit()

            # Ensure user is properly bound to session before login
            user = db.session.merge(user)

            # Log the user in
            login_user(user, remember=True)
            flash('Account created successfully! Welcome to mdraft.', 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred creating your account. Please try again.', 'error')
            return render_template('signup.html')

    return render_template('signup.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    """User login endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        # Validation
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('login.html')

        # Find user and verify password
        user = User.query.filter_by(email=email).first()

        if not user or not user.verify_password(password):
            flash('Invalid email or password', 'error')
            return render_template('login.html')

        if not user.is_active:
            flash('Account is disabled', 'error')
            return render_template('login.html')

        # Ensure user is properly bound to session before login
        user = db.session.merge(user)

        # Login successful
        login_user(user, remember=remember)
        flash(f'Welcome back, {user.email}!', 'success')

        # Redirect to next page or home
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('main.index'))

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    """User logout endpoint."""
    # Ensure we have a fresh user object bound to the session
    user = User.get_user_safely(current_user.id)
    user_email = user.email if user else 'User'
    logout_user()
    flash(f'Goodbye, {user_email}!', 'info')
    return redirect(url_for('main.index'))


@auth.route('/account')
@login_required
def account():
    """User account dashboard."""
    try:
        # Get user directly from database to ensure fresh session
        user = User.query.get(current_user.id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('main.index'))
        
        # Ensure user is properly bound to session
        user = db.session.merge(user)
        
        # Get user statistics using the fresh user object
        total_conversions = user.conversions.count()
        daily_conversions = user.get_daily_conversions()

        # Get recent conversions - ensure it's always a list
        try:
            recent_conversions = user.conversions.order_by(
                Conversion.created_at.desc()
            ).limit(10).all()
            # Ensure it's a list, not a single value
            if not isinstance(recent_conversions, list):
                recent_conversions = []
        except Exception as e:
            current_app.logger.error(f"Error getting recent conversions: {e}")
            recent_conversions = []

        # Calculate success rate - ensure it's a number
        try:
            successful_conversions = user.conversions.filter_by(status='completed').count()
            success_rate = (successful_conversions / total_conversions * 100) if total_conversions > 0 else 0
            # Ensure it's a number, not a float that might be passed as iterable
            success_rate = float(success_rate) if success_rate is not None else 0.0
        except Exception as e:
            current_app.logger.error(f"Error calculating success rate: {e}")
            success_rate = 0.0

        # Calculate Pro conversions count - ensure it's a number
        try:
            pro_conversions_count = user.conversions.filter_by(conversion_type='pro').count()
            pro_conversions_count = int(pro_conversions_count) if pro_conversions_count is not None else 0
        except Exception as e:
            current_app.logger.error(f"Error calculating pro conversions count: {e}")
            pro_conversions_count = 0

        # Calculate average processing time for completed conversions - ensure it's a number
        try:
            completed_conversions = user.conversions.filter_by(status='completed').filter(
                Conversion.processing_time.isnot(None)
            ).all()
            
            if completed_conversions and isinstance(completed_conversions, list):
                total_time = sum(conv.processing_time for conv in completed_conversions if conv.processing_time is not None)
                avg_processing_time = total_time / len(completed_conversions) if completed_conversions else 0.0
            else:
                avg_processing_time = 0.0
            # Ensure it's a number
            avg_processing_time = float(avg_processing_time) if avg_processing_time is not None else 0.0
        except Exception as e:
            current_app.logger.error(f"Error calculating average processing time: {e}")
            avg_processing_time = 0.0

        # Monthly allowance for Pro users
        from app.tasks import MONTHLY_PAGE_ALLOWANCE
        monthly_allowance = MONTHLY_PAGE_ALLOWANCE
        
        # Generate API key if user doesn't have one
        if not user.api_key:
            user.generate_api_key()
        
        return render_template('auth/account.html',
                             user=user,
                             total_conversions=total_conversions,
                             daily_conversions=daily_conversions,
                             recent_conversions=recent_conversions,
                             success_rate=round(success_rate, 1),
                             pro_conversions_count=pro_conversions_count,
                             avg_processing_time=round(avg_processing_time, 1),
                             trial_days_remaining=user.trial_days_remaining,
                             pro_pages_processed=getattr(user, 'pro_pages_processed_current_month', 0),
                             monthly_allowance=monthly_allowance)
    except Exception as e:
        # Log the error for debugging
        current_app.logger.error(f"Error in account route: {e}")
        flash('An error occurred loading your account. Please try again.', 'error')
        return redirect(url_for('main.index'))


@auth.route('/test-email')
@login_required
def test_email():
    """Test email functionality."""
    try:
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.account'))
        
        # Ensure user is properly bound to session
        user = db.session.merge(user)
        
        from app.email import send_conversion_complete_email
        send_conversion_complete_email(user.email, "test-file.pdf")
        flash('Test email sent successfully!', 'success')
    except Exception as e:
        flash(f'Email test failed: {str(e)}', 'error')
    return redirect(url_for('auth.account'))

@auth.route('/api-key/generate', methods=['POST'])
@login_required
def generate_api_key():
    """Generate a new API key for the current user."""
    try:
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.account'))
        
        # Ensure user is properly bound to session
        user = db.session.merge(user)
        
        user.generate_api_key()
        flash('New API key generated successfully!', 'success')
    except Exception as e:
        flash(f'Failed to generate API key: {str(e)}', 'error')
    return redirect(url_for('auth.account'))

@auth.route('/api-key/revoke', methods=['POST'])
@login_required
def revoke_api_key():
    """Revoke the current API key."""
    try:
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.account'))
        
        # Ensure user is properly bound to session
        user = db.session.merge(user)
        
        user.revoke_api_key()
        flash('API key revoked successfully!', 'success')
    except Exception as e:
        flash(f'Failed to revoke API key: {str(e)}', 'error')
    return redirect(url_for('auth.account'))

@auth.route('/user-status')
def user_status():
    """API endpoint to get current user status."""
    if current_user.is_authenticated:
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Ensure user is properly bound to session
        user = db.session.merge(user)
        
        # Get user's conversion stats using the fresh user object
        daily_conversions = user.get_daily_conversions()
        
        # Handle total conversions count safely
        if hasattr(user, '_conversion_ids'):
            # Fallback case - use the pre-loaded conversion IDs
            total_conversions = len(user._conversion_ids)
        else:
            # Normal case with relationship loaded
            total_conversions = user.conversions.count()

        return jsonify({
            'authenticated': True,
            'email': user.email,
            'is_premium': user.is_premium,
            'has_pro_access': user.has_pro_access,
            'on_trial': getattr(user, 'on_trial', False),
            'trial_days_remaining': user.trial_days_remaining,
            'daily_conversions': daily_conversions,
            'total_conversions': total_conversions,
            'can_convert': user.can_convert()
        })
    else:
        # Anonymous user status
        session_id = session.get('session_id')
        if session_id:
            usage = AnonymousUsage.query.filter_by(session_id=session_id).first()
            if usage:
                return jsonify({
                    'authenticated': False,
                    'daily_conversions': usage.conversions_today,
                    'daily_limit': 5,
                    'can_convert': usage.can_convert(),
                    'remaining': max(0, 5 - usage.conversions_today)
                })

        return jsonify({
            'authenticated': False,
            'daily_conversions': 0,
            'daily_limit': 5,
            'can_convert': True,
            'remaining': 5
        })

# --- Stripe Integration Routes (FUNCTION-LEVEL IMPORTS ONLY) ---

@auth.route('/upgrade')
@login_required
def upgrade():
    """Upgrade to premium page."""
    # Ensure we have a fresh user object bound to the session
    user = User.get_user_safely(current_user.id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.account'))
    
    # Ensure user is properly bound to session
    user = db.session.merge(user)
    
    if user.is_premium:
        flash('You are already on the Pro plan!', 'info')
        return redirect(url_for('auth.account'))
    return render_template('auth/upgrade.html')

@auth.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Create a Stripe Checkout session for the user to pay."""
    try:
        # Import stripe ONLY when this function is called
        import stripe
    except ImportError:
        flash('Payment system is currently unavailable. Please try again later.', 'error')
        return redirect(url_for('auth.upgrade'))
    
    try:
        # Ensure we have a fresh user object bound to the session
        user = User.get_user_safely(current_user.id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.upgrade'))
        
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': current_app.config['STRIPE_PRICE_ID'],
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=url_for('auth.stripe_success', _external=True),
            cancel_url=url_for('auth.upgrade', _external=True),
            customer_email=user.email,
            client_reference_id=user.id,
            subscription_data={
                "metadata": {
                    "user_id": user.id
                }
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Error connecting to payment gateway: {str(e)}', 'error')
        return redirect(url_for('auth.upgrade'))

@auth.route('/stripe-success')
@login_required
def stripe_success():
    """Handle successful payment redirect."""
    flash('Payment successful! Welcome to mdraft Pro.', 'success')
    return redirect(url_for('auth.account'))

@auth.route('/billing-portal', methods=['POST'])
@login_required
def billing_portal():
    """Redirect user to Stripe Customer Billing Portal."""
    # Ensure we have a fresh user object bound to the session
    user = User.get_user_safely(current_user.id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.account'))
    
    if not user.stripe_customer_id:
        flash("You don't have a billing account with us.", "error")
        return redirect(url_for('auth.account'))

    try:
        # Import stripe ONLY when this function is called
        import stripe
    except ImportError:
        flash('Billing system is currently unavailable. Please try again later.', 'error')
        return redirect(url_for('auth.account'))

    try:
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=url_for('auth.account', _external=True)
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f'Error accessing billing portal: {str(e)}', 'error')
        return redirect(url_for('auth.account'))

@auth.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Comprehensive webhook handler for the entire Stripe subscription lifecycle."""
    try:
        # Import stripe ONLY when this function is called
        import stripe
    except ImportError:
        current_app.logger.error("Stripe webhook called but stripe module not available")
        return 'Stripe not available', 503

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = current_app.config['STRIPE_WEBHOOK_SECRET']

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=webhook_secret
        )
    except ValueError as e:
        current_app.logger.error(f"Invalid payload in webhook: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.error(f"Invalid signature in webhook: {e}")
        return 'Invalid signature', 400

    event_type = event['type']
    current_app.logger.info(f"Processing Stripe webhook event: {event_type}")

    try:
        # 1. Handle invoice.payment_succeeded
        if event_type == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            customer_id = invoice.get('customer')
            subscription_id = invoice.get('subscription')
            amount_paid = invoice.get('amount_paid', 0) / 100  # Convert from cents
            
            try:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user:
                    # Update subscription status and payment dates
                    user.subscription_status = 'active'
                    user.last_payment_date = datetime.now(timezone.utc)
                    
                    # Determine tier based on subscription
                    if subscription_id:
                        try:
                            subscription = stripe.Subscription.retrieve(subscription_id)
                            price_id = subscription.get('items', {}).get('data', [{}])[0].get('price', {}).get('id')
                            
                            # Map price ID to tier (you may need to adjust these based on your Stripe setup)
                            if 'pro' in price_id.lower():
                                user.current_tier = 'pro'
                            elif 'enterprise' in price_id.lower():
                                user.current_tier = 'enterprise'
                            else:
                                user.current_tier = 'pro'  # Default fallback
                        except Exception as e:
                            current_app.logger.error(f"Error retrieving subscription {subscription_id}: {e}")
                            user.current_tier = 'pro'  # Default fallback
                    
                    # Set subscription start date if not already set
                    if not user.subscription_start_date:
                        user.subscription_start_date = datetime.now(timezone.utc)
                    
                    # Ensure premium status
                    user.is_premium = True
                    user.on_trial = False
                    
                    db.session.commit()
                    current_app.logger.info(f"Payment succeeded for user {user.email}: ${amount_paid}")
                else:
                    current_app.logger.warning(f"Payment succeeded for unknown customer: {customer_id}")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error processing payment_succeeded for customer {customer_id}: {e}")

        # 2. Handle invoice.payment_failed
        elif event_type == 'invoice.payment_failed':
            invoice = event['data']['object']
            customer_id = invoice.get('customer')
            amount_due = invoice.get('amount_due', 0) / 100  # Convert from cents
            
            try:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user:
                    current_app.logger.warning(
                        f"Payment failed for user {user.email} (ID: {user.id}). "
                        f"Amount due: ${amount_due}. Customer ID: {customer_id}"
                    )
                    # Note: We don't downgrade immediately on payment failure
                    # Stripe will handle retries and send subscription.updated events
                else:
                    current_app.logger.warning(f"Payment failed for unknown customer: {customer_id}")
            except Exception as e:
                current_app.logger.error(f"Error processing payment_failed for customer {customer_id}: {e}")

        # 3. Handle customer.subscription.updated (Primary state synchronization)
        elif event_type == 'customer.subscription.updated':
            subscription = event['data']['object']
            subscription_id = subscription.get('id')
            status = subscription.get('status')
            customer_id = subscription.get('customer')
            
            try:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user:
                    if status == 'active':
                        # Subscription is active - ensure user has premium access
                        try:
                            user.is_premium = True
                            user.on_trial = False
                            user.subscription_status = 'active'
                            db.session.commit()
                            current_app.logger.info(f"Subscription activated for user {user.email}")
                        except Exception as e:
                            db.session.rollback()
                            current_app.logger.error(f"Error activating subscription for user {user.id}: {e}")
                    
                    elif status in ['past_due', 'unpaid']:
                        # Subscription is past due - downgrade user
                        try:
                            user.is_premium = False
                            user.on_trial = False
                            user.subscription_status = 'past_due'
                            db.session.commit()
                            current_app.logger.warning(f"Subscription downgraded for user {user.email} (status: {status})")
                        except Exception as e:
                            db.session.rollback()
                            current_app.logger.error(f"Error downgrading subscription for user {user.id}: {e}")
                    
                    elif status == 'canceled':
                        # Subscription is canceled
                        try:
                            user.is_premium = False
                            user.on_trial = False
                            user.subscription_status = 'canceled'
                            db.session.commit()
                            current_app.logger.info(f"Subscription canceled for user {user.email}")
                        except Exception as e:
                            db.session.rollback()
                            current_app.logger.error(f"Error canceling subscription for user {user.id}: {e}")
                else:
                    current_app.logger.warning(f"Subscription updated for unknown customer: {customer_id}")
            except Exception as e:
                current_app.logger.error(f"Error processing subscription.updated for customer {customer_id}: {e}")

        # 4. Handle customer.subscription.deleted (Consolidated logic)
        elif event_type == 'customer.subscription.deleted':
            subscription = event['data']['object']
            subscription_id = subscription.get('id')
            customer_id = subscription.get('customer')
            
            try:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user:
                    try:
                        user.is_premium = False
                        user.on_trial = False
                        user.subscription_status = 'canceled'
                        # Optionally clear stripe IDs (uncomment if needed)
                        # user.stripe_customer_id = None
                        # user.stripe_subscription_id = None
                        db.session.commit()
                        current_app.logger.info(f"Subscription deleted for user {user.email}")
                    except Exception as e:
                        db.session.rollback()
                        current_app.logger.error(f"Error processing subscription deletion for user {user.id}: {e}")
                else:
                    current_app.logger.warning(f"Subscription deleted for unknown customer: {customer_id}")
            except Exception as e:
                current_app.logger.error(f"Error processing subscription.deleted for customer {customer_id}: {e}")

        # 5. Handle checkout.session.completed (Legacy support)
        elif event_type == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session.get('client_reference_id')
            stripe_customer_id = session.get('customer')
            stripe_subscription_id = session.get('subscription')

            try:
                user = User.query.get(user_id)
                if user:
                    try:
                        user.is_premium = True
                        user.stripe_customer_id = stripe_customer_id
                        user.stripe_subscription_id = stripe_subscription_id
                        user.subscription_status = 'active'
                        user.subscription_start_date = datetime.now(timezone.utc)
                        user.last_payment_date = datetime.now(timezone.utc)
                        user.on_trial = False
                        db.session.commit()
                        current_app.logger.info(f"Checkout completed for user {user.email}")
                    except Exception as e:
                        db.session.rollback()
                        current_app.logger.error(f"Error processing checkout completion for user {user_id}: {e}")
                else:
                    current_app.logger.warning(f"Checkout completed for unknown user: {user_id}")
            except Exception as e:
                current_app.logger.error(f"Error processing checkout.session.completed: {e}")

        else:
            # Log unhandled event types for monitoring
            current_app.logger.info(f"Unhandled Stripe webhook event type: {event_type}")

    except Exception as e:
        current_app.logger.error(f"Unexpected error in webhook handler: {e}")
        return 'Internal server error', 500

    return 'OK', 200