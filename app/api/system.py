"""System endpoints: alerts, settings, cameras, zones, reports and data management."""
import csv
import io
from datetime import datetime, timedelta

import cv2
from flask import Response, jsonify, request
from flask_login import current_user, login_required

from ..ai.video_processor import camera_manager, parse_source
from ..decorators import admin_required
from ..extensions import db
from ..models import Activity, Alert, Camera, HeatmapCell, Report, Setting, TrafficSample, Visit, Zone
from ..services.reports import REPORT_TYPES, generate_report
from . import api_bp


# ---------------------------------------------------------------- alerts
@api_bp.get("/system/alerts")
@login_required
def system_alerts():
    include_resolved = request.args.get("all") == "1"
    query = Alert.query if include_resolved else Alert.query.filter_by(resolved=False)
    return jsonify([a.to_dict() for a in query.order_by(Alert.created_at.desc()).limit(50)])


@api_bp.post("/system/alerts/<int:alert_id>/resolve")
@login_required
def resolve_alert(alert_id):
    alert = db.get_or_404(Alert, alert_id)
    alert.resolved = True
    db.session.commit()
    return jsonify(alert.to_dict())


# ---------------------------------------------------------------- settings
def _validate_settings(payload: dict) -> dict:
    clean = {}
    if "detection_confidence" in payload:
        value = float(payload["detection_confidence"])
        if not 0.1 <= value <= 1.0:
            raise ValueError("Detection confidence must be between 0.1 and 1.0")
        clean["detection_confidence"] = f"{value:.2f}"
    for key in ("enable_tracking", "enable_recording", "enable_email_alerts"):
        if key in payload:
            clean[key] = "true" if payload[key] in (True, "true", "on", "1") else "false"
    if "data_retention_days" in payload:
        days = int(payload["data_retention_days"])
        if not 1 <= days <= 3650:
            raise ValueError("Retention must be between 1 and 3650 days")
        clean["data_retention_days"] = str(days)
    if "crowd_threshold" in payload:
        clean["crowd_threshold"] = str(max(1, int(payload["crowd_threshold"])))
    for key in ("recording_path", "alert_email"):
        if key in payload:
            clean[key] = str(payload[key]).strip()[:255]
    return clean


@api_bp.get("/system/settings")
@login_required
@admin_required
def get_settings():
    return jsonify(Setting.as_dict())


@api_bp.post("/system/settings")
@login_required
@admin_required
def save_settings():
    try:
        clean = _validate_settings(request.get_json(force=True) or {})
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    for key, value in clean.items():
        Setting.put(key, value)
    db.session.commit()
    return jsonify(Setting.as_dict())


@api_bp.post("/system/settings/reset")
@login_required
@admin_required
def reset_settings():
    Setting.query.delete()
    db.session.commit()
    return jsonify(Setting.as_dict())


# ---------------------------------------------------------------- data management
@api_bp.post("/system/cleanup")
@login_required
@admin_required
def cleanup_data():
    days = int(Setting.get("data_retention_days"))
    cutoff = datetime.now() - timedelta(days=days)
    removed = {
        "visits": Visit.query.filter(Visit.entered_at < cutoff).delete(),
        "samples": TrafficSample.query.filter(TrafficSample.timestamp < cutoff).delete(),
        "heatmap_cells": HeatmapCell.query.filter(HeatmapCell.day < cutoff.date()).delete(),
    }
    db.session.commit()
    return jsonify(removed=removed, cutoff=cutoff.isoformat())


@api_bp.get("/system/export")
@login_required
@admin_required
def export_data():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["visit_id", "track_id", "zone", "camera_id", "entered_at", "exited_at", "dwell_seconds"])
    for v in Visit.query.order_by(Visit.entered_at):
        writer.writerow([v.id, v.track_id, v.zone.name if v.zone else "", v.camera_id,
                         v.entered_at.isoformat(), v.exited_at.isoformat() if v.exited_at else "",
                         round(v.dwell_seconds, 1)])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=shopmotion_visits.csv"})


# ---------------------------------------------------------------- cameras
def _camera_from_payload(camera: Camera, data: dict) -> None:
    camera.name = str(data.get("name", camera.name or "")).strip()[:64] or "Camera"
    camera.location = str(data.get("location", camera.location or "")).strip()[:64]
    camera.source = str(data.get("source", camera.source or "0")).strip()[:256] or "0"
    if "resolution" in data and "x" in str(data["resolution"]):
        w, h = str(data["resolution"]).lower().split("x", 1)
        camera.width, camera.height = int(w), int(h)
    if "fps" in data:
        camera.fps = max(1, min(int(data["fps"]), 120))
    if "enabled" in data:
        camera.enabled = bool(data["enabled"])


@api_bp.get("/system/cameras")
@login_required
def list_cameras():
    running = set(camera_manager.running_ids())
    return jsonify([{**c.to_dict(), "running": c.id in running} for c in Camera.query.order_by(Camera.id)])


@api_bp.post("/system/cameras")
@login_required
@admin_required
def add_camera():
    camera = Camera()
    try:
        _camera_from_payload(camera, request.get_json(force=True) or {})
    except (TypeError, ValueError):
        return jsonify(error="Invalid camera settings"), 400
    db.session.add(camera)
    db.session.commit()
    return jsonify(camera.to_dict()), 201


@api_bp.put("/system/cameras/<int:camera_id>")
@login_required
@admin_required
def update_camera(camera_id):
    camera = db.get_or_404(Camera, camera_id)
    try:
        _camera_from_payload(camera, request.get_json(force=True) or {})
    except (TypeError, ValueError):
        return jsonify(error="Invalid camera settings"), 400
    db.session.commit()
    return jsonify(camera.to_dict())


@api_bp.delete("/system/cameras/<int:camera_id>")
@login_required
@admin_required
def delete_camera(camera_id):
    camera = db.get_or_404(Camera, camera_id)
    camera_manager.stop(camera_id)
    db.session.delete(camera)
    db.session.commit()
    return jsonify(status="deleted")


@api_bp.post("/system/cameras/<int:camera_id>/test")
@login_required
@admin_required
def test_camera(camera_id):
    camera = db.get_or_404(Camera, camera_id)
    if camera.id in camera_manager.running_ids():
        return jsonify(ok=True, message="Camera is running")
    cap = cv2.VideoCapture(parse_source(camera.source))
    ok, frame = cap.read() if cap.isOpened() else (False, None)
    cap.release()
    if not ok:
        return jsonify(ok=False, message=f"Could not read a frame from '{camera.source}'")
    h, w = frame.shape[:2]
    return jsonify(ok=True, message=f"Camera OK — received a {w}x{h} frame")


@api_bp.post("/system/cameras/detect")
@login_required
@admin_required
def detect_cameras():
    """Probe the first few local device indexes for attached USB cameras."""
    configured = {c.source: c.id for c in Camera.query.all()}
    running = set(camera_manager.running_ids())
    found = []
    for index in range(5):
        if configured.get(str(index)) in running:  # opening it again would fail
            found.append({"index": index, "in_use": True})
            continue
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append({"index": index, "in_use": str(index) in configured})
        cap.release()
    return jsonify(found)


# ---------------------------------------------------------------- zones
@api_bp.get("/system/zones")
@login_required
def list_zones():
    return jsonify([z.to_dict() for z in Zone.query.order_by(Zone.id)])


@api_bp.put("/system/zones")
@login_required
@admin_required
def save_zones():
    """Replace the store layout. Zones keep their id when it is supplied."""
    payload = request.get_json(force=True) or []
    if not isinstance(payload, list):
        return jsonify(error="Expected a list of zones"), 400
    keep_ids = set()
    for item in payload:
        try:
            values = {k: min(max(float(item[k]), 0.0), 1.0) for k in ("x", "y", "w", "h")}
            name = str(item["name"]).strip()[:64]
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Each zone needs name, x, y, w, h"), 400
        if not name:
            return jsonify(error="Zone names cannot be empty"), 400
        zone = db.session.get(Zone, item.get("id")) if item.get("id") else None
        if zone is None:
            zone = Zone(name=name, **values)
            db.session.add(zone)
        zone.name, zone.color = name, str(item.get("color", zone.color or "#667eea"))[:9]
        for k, v in values.items():
            setattr(zone, k, v)
        db.session.flush()
        keep_ids.add(zone.id)
    for zone in Zone.query.all():
        if zone.id not in keep_ids:
            Visit.query.filter_by(zone_id=zone.id).delete()
            db.session.delete(zone)
    db.session.commit()
    return jsonify([z.to_dict() for z in Zone.query.order_by(Zone.id)])


# ---------------------------------------------------------------- reports
@api_bp.post("/reports")
@login_required
def create_report():
    data = request.get_json(force=True) or {}
    report_type = data.get("type", "summary")
    if report_type not in REPORT_TYPES:
        return jsonify(error="Unknown report type"), 400
    try:
        report = generate_report(report_type, data.get("period", "week"), current_user,
                                 data.get("start") or None, data.get("end") or None)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(id=report.id, title=report.title), 201


@api_bp.delete("/reports/<int:report_id>")
@login_required
def delete_report(report_id):
    report = db.get_or_404(Report, report_id)
    if report.created_by != current_user.id and not current_user.is_admin:
        return jsonify(error="Only the author or an admin can delete this report"), 403
    db.session.delete(report)
    db.session.commit()
    return jsonify(status="deleted")


@api_bp.get("/system/activity")
@login_required
def recent_activity():
    items = Activity.query.order_by(Activity.created_at.desc()).limit(20)
    return jsonify([{"kind": a.kind, "icon": a.icon, "title": a.title, "message": a.message,
                     "created_at": a.created_at.isoformat()} for a in items])
