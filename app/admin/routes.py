from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import User, Conversion, db
from datetime import datetime, timedelta, timezone

admin = Blueprint('admin', __name__)

@admin.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard."""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.index'))
    
    # Get conversion statistics
    total_conversions = Conversion.query.count()
    recent_conversions = Conversion.query.order_by(Conversion.created_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                         total_conversions=total_conversions,
                         recent_conversions=recent_conversions)

@admin.route('/upgrade-user', methods=['GET', 'POST'])
@login_required
def upgrade_user():
    """Upgrade a user to pro status for testing."""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email is required.', 'error')
            return render_template('admin/upgrade_user.html')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash(f'User with email {email} not found.', 'error')
            return render_template('admin/upgrade_user.html')
        
        # Set up pro access
        user.is_premium = True
        user.subscription_status = 'active'
        user.current_tier = 'pro'
        user.subscription_start_date = datetime.now(timezone.utc)
        user.last_payment_date = datetime.now(timezone.utc)
        user.next_payment_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Set trial to active (for testing purposes)
        user.on_trial = True
        user.trial_start_date = datetime.now(timezone.utc)
        user.trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Reset usage tracking
        user.pro_pages_processed_current_month = 0
        
        try:
            db.session.commit()
            flash(f'Successfully upgraded {email} to PRO status!', 'success')
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error upgrading user: {e}', 'error')
            return render_template('admin/upgrade_user.html')
    
    return render_template('admin/upgrade_user.html') 