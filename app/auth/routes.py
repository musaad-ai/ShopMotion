from datetime import datetime
from urllib.parse import urlsplit

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from . import auth_bp
from .forms import LoginForm, RegisterForm


def _safe_next(target: str | None) -> str:
    # Only allow relative redirects to prevent open-redirect attacks.
    if target and not urlsplit(target).netloc and target.startswith("/"):
        return target
    return url_for("main.dashboard")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password.", "danger")
        elif not user.is_active:
            flash("This account has been disabled.", "danger")
        else:
            login_user(user, remember=form.remember.data)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html", form=form,
                           allow_registration=current_app.config["ALLOW_REGISTRATION"])


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["ALLOW_REGISTRATION"]:
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        # The very first account becomes the administrator.
        role = "admin" if User.query.count() == 0 else "viewer"
        user = User(username=form.username.data.strip(), email=form.email.data.lower(), role=role)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Account created. You can sign in now.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
