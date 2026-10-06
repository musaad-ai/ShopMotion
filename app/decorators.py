from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(view):
    """Role-based access control: only users with the ``admin`` role pass."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper
