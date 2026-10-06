"""Real-time endpoints: start/stop cameras, MJPEG stream, live detection stats."""
import time

from flask import Response, current_app, jsonify, request, send_file
from flask_login import login_required

from ..ai.video_processor import camera_manager
from ..extensions import db
from ..models import Activity, Camera, Zone
from . import api_bp


def _camera_or_404(camera_id):
    camera = db.session.get(Camera, camera_id)
    if camera is None:
        return None, (jsonify(error="Camera not found"), 404)
    return camera, None


@api_bp.post("/live/start/<int:camera_id>")
@login_required
def live_start(camera_id):
    camera, err = _camera_or_404(camera_id)
    if err:
        return err
    if not camera.enabled:
        return jsonify(error="Camera is disabled"), 400
    app = current_app._get_current_object()
    proc = camera_manager.start(app, camera, Zone.query.all())
    # Give the capture thread a moment to report an open failure.
    time.sleep(0.8)
    if proc.error:
        camera_manager.stop(camera_id)
        return jsonify(error=proc.error), 503
    db.session.add(Activity(kind="success", icon="fa-video", title="Camera started",
                            message=f"{camera.name} monitoring started"))
    db.session.commit()
    return jsonify(status="started", **proc.stats())


@api_bp.post("/live/stop/<int:camera_id>")
@login_required
def live_stop(camera_id):
    camera_manager.stop(camera_id)
    return jsonify(status="stopped")


@api_bp.get("/live/stream/<int:camera_id>")
@login_required
def live_stream(camera_id):
    proc = camera_manager.get(camera_id)
    if proc is None or not proc.running:
        return jsonify(error="Camera is not running"), 404

    def frames():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while proc.running:
            data = proc.latest_jpeg()
            if data:
                yield boundary + data + b"\r\n"
            time.sleep(1 / 20)

    return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@api_bp.get("/live/detect")
@api_bp.get("/live/detect/<int:camera_id>")
@login_required
def live_detect(camera_id=None):
    """Live statistics + detection log for one camera (or the first running one)."""
    camera_id = camera_id or request.args.get("camera_id", type=int)
    if camera_id is None:
        running = camera_manager.running_ids()
        camera_id = running[0] if running else None
    proc = camera_manager.get(camera_id) if camera_id else None
    if proc is None:
        return jsonify(running=False, current_visitors=0, total_detected=0, peak_count=0,
                       avg_dwell_seconds=0, log=[])
    return jsonify(camera_id=camera_id, log=list(proc.detection_log), **proc.stats())


@api_bp.post("/live/snapshot/<int:camera_id>")
@login_required
def live_snapshot(camera_id):
    proc = camera_manager.get(camera_id)
    if proc is None or not proc.running:
        return jsonify(error="Camera is not running"), 404
    path = proc.snapshot(current_app.config["SNAPSHOT_DIR"])
    if path is None:
        return jsonify(error="No frame available yet"), 409
    return send_file(path, mimetype="image/jpeg", as_attachment=True, download_name=path.name)
