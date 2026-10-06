import json
import platform

import cv2
from flask import Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..auth.forms import UserAdminForm
from ..decorators import admin_required
from ..extensions import db
from ..models import Activity, Alert, Camera, Report, Setting, User, Zone
from ..services import analytics
from ..services.reports import REPORT_TYPES, report_to_csv
from . import main_bp


@main_bp.route("/")
@login_required
def dashboard():
    return render_template(
        "dashboard.html", page="dashboard", title="Dashboard Overview",
        summary=analytics.dashboard_summary(),
        zones=[z.to_dict() for z in Zone.query.order_by(Zone.id)],
        alerts=Alert.query.filter_by(resolved=False).order_by(Alert.created_at.desc()).limit(4).all(),
        activity=Activity.query.order_by(Activity.created_at.desc()).limit(8).all(),
    )


@main_bp.route("/live")
@login_required
def live():
    cameras = Camera.query.filter_by(enabled=True).order_by(Camera.id).all()
    return render_template("live.html", page="live", title="Live Monitoring", cameras=cameras)


@main_bp.route("/analytics/traffic")
@login_required
def traffic():
    return render_template("traffic.html", page="traffic", title="Traffic Analytics")


@main_bp.route("/analytics/heatmap")
@login_required
def heatmap():
    return render_template("heatmap.html", page="heatmap", title="Heatmap Analysis")


@main_bp.route("/analytics/dwell")
@login_required
def dwell():
    return render_template("dwell.html", page="dwell", title="Dwell Time Analysis")


@main_bp.route("/reports")
@login_required
def reports():
    items = Report.query.order_by(Report.created_at.desc()).all()
    return render_template("reports.html", page="reports", title="Reports Center",
                           reports=items, report_types=REPORT_TYPES)


@main_bp.route("/reports/<int:report_id>")
@login_required
def report_view(report_id):
    report = db.get_or_404(Report, report_id)
    return render_template("report_view.html", page="reports", title=report.title,
                           report=report, data=json.loads(report.data_json))


@main_bp.route("/reports/<int:report_id>/download")
@login_required
def report_download(report_id):
    report = db.get_or_404(Report, report_id)
    filename = f"shopmotion_{report.report_type}_{report.created_at:%Y%m%d}_{report.id}.csv"
    return Response(report_to_csv(report), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@main_bp.route("/store-layout")
@login_required
@admin_required
def store_layout():
    zones = [z.to_dict() for z in Zone.query.order_by(Zone.id)]
    return render_template("store_layout.html", page="layout", title="Store Layout", zones=zones)


@main_bp.route("/cameras")
@login_required
@admin_required
def cameras():
    return render_template("cameras.html", page="cameras", title="Camera Setup",
                           cameras=Camera.query.order_by(Camera.id).all())


@main_bp.route("/settings")
@login_required
@admin_required
def settings():
    info = {
        "opencv": cv2.__version__,
        "python": platform.python_version(),
        "cameras": Camera.query.count(),
        "zones": Zone.query.count(),
    }
    return render_template("settings.html", page="settings", title="System Settings",
                           settings=Setting.as_dict(), info=info)


@main_bp.route("/admin/users", methods=["GET"])
@login_required
@admin_required
def users():
    return render_template("admin/users.html", page="users", title="User Management",
                           users=User.query.order_by(User.id).all(), form=UserAdminForm())


@main_bp.route("/admin/users/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def update_user(user_id):
    user = db.get_or_404(User, user_id)
    form = UserAdminForm()
    if not form.validate_on_submit():
        abort(400)
    if user.id == current_user.id and (form.role.data != "admin" or not form.active.data):
        flash("You cannot demote or disable your own account.", "warning")
    else:
        user.role, user.active = form.role.data, form.active.data
        db.session.commit()
        flash(f"Updated {user.username}.", "success")
    return redirect(url_for("main.users"))
