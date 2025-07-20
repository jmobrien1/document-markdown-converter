from flask import render_template, abort
from flask_login import login_required, current_user
from . import admin
from ..models import User

@admin.route('/admin/dashboard')
@login_required
def dashboard():
    """
    Render the admin dashboard page for users with admin privileges.

    Returns:
        Response: The rendered admin dashboard template with a list of all users.

    Raises:
        403: If the current user is not an admin.
    """
    if not getattr(current_user, 'is_admin', False):
        abort(403)
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/dashboard.html', users=users) 