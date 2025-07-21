from flask import render_template, abort
from flask_login import login_required, current_user
from . import admin
from ..models import User
from app.decorators import admin_required

@admin.route('/admin/dashboard')
@login_required
@admin_required
def dashboard():
    """
    Render the admin dashboard page for users with admin privileges.

    Returns:
        Response: The rendered admin dashboard template with a list of all users.
    """
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/dashboard.html', users=users) 