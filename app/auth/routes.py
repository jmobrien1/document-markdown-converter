# app/auth/routes.py
# Enhanced with Stripe payment integration

import re
import stripe
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
            # Create new user
            user = User(email=email)
            user.password = password  # Uses the setter

            db.session.add(user)
            db.session.commit()

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
    user_email = current_user.email
    logout_user()
    flash(f'Goodbye, {user_email}!', 'info')
    return redirect(url_for('main.index'))


@auth.route('/account')
@login_required
def account():
    """User account dashboard."""
    # Get user statistics
    total_conversions = current_user.conversions.count()
    daily_conversions = current_user.get_daily_conversions()

    # Get recent conversions
    recent_conversions = current_user.conversions.order_by(
        Conversion.created_at.desc()
    ).limit(10).all()

    # Calculate success rate
    successful_conversions = current_user.conversions.filter_by(status='completed').count()
    success_rate = (successful_conversions / total_conversions * 100) if total_conversions > 0 else 0

    return render_template('auth/account.html',
                         user=current_user,
                         total_conversions=total_conversions,
                         daily_conversions=daily_conversions,
                         recent_conversions=recent_conversions,
                         success_rate=round(success_rate, 1))


@auth.route('/user-status')
def user_status():
    """API endpoint to get current user status."""
    if current_user.is_authenticated:
        # Get user's conversion stats
        daily_conversions = current_user.get_daily_conversions()
        total_conversions = current_user.conversions.count()

        return jsonify({
            'authenticated': True,
            'email': current_user.email,
            'is_premium': current_user.is_premium,
            'daily_conversions': daily_conversions,
            'total_conversions': total_conversions,
            'can_convert': current_user.can_convert()
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

# --- Stripe Integration Routes ---

@auth.route('/upgrade')
@login_required
def upgrade():
    """Upgrade to premium page."""
    if current_user.is_premium:
        flash('You are already on the Pro plan!', 'info')
        return redirect(url_for('auth.account'))
    return render_template('auth/upgrade.html')

@auth.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Create a Stripe Checkout session for the user to pay."""
    try:
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
            customer_email=current_user.email,
            client_reference_id=current_user.id,
            subscription_data={
                "metadata": {
                    "user_id": current_user.id
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
    if not current_user.stripe_customer_id:
        flash("You don't have a billing account with us.", "error")
        return redirect(url_for('auth.account'))

    try:
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for('auth.account', _external=True)
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f'Error accessing billing portal: {str(e)}', 'error')
        return redirect(url_for('auth.account'))

@auth.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Listen for events from Stripe."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = current_app.config['STRIPE_WEBHOOK_SECRET']

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return 'Invalid signature', 400

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('client_reference_id')
        stripe_customer_id = session.get('customer')
        stripe_subscription_id = session.get('subscription')

        user = User.query.get(user_id)
        if user:
            user.is_premium = True
            user.stripe_customer_id = stripe_customer_id
            user.stripe_subscription_id = stripe_subscription_id
            db.session.commit()
            current_app.logger.info(f"User {user_id} successfully upgraded to Pro.")

    # Handle subscription cancellation
    if event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_subscription_id = subscription.get('id')

        user = User.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
        if user:
            user.is_premium = False
            # Optionally clear stripe IDs
            # user.stripe_customer_id = None
            # user.stripe_subscription_id = None
            db.session.commit()
            current_app.logger.info(f"User {user.id} subscription canceled.")

    return 'OK', 200