"""End-to-end test of the capture pipeline on a generated video file.

A stub detector finds the white rectangle that walks across the frame, so the
test exercises capture, tracking, zone visits and database writes without
needing model weights or a camera.
"""
import time

import cv2
import numpy as np

from app.ai import video_processor as vp
from app.ai.detector import Detection
from app.ai.tracker import CentroidTracker
from app.models import Camera, HeatmapCell, TrafficSample, Visit, Zone


class BlobDetector:
    name = "test-blob"

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours((gray > 200).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            out.append(Detection(x, y, x + w, y + h, 0.99))
        return out


def make_video(path, frames=240, size=(320, 180)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, size)
    for i in range(frames):
        frame = np.zeros((size[1], size[0], 3), np.uint8)
        x = int(10 + (size[0] - 40) * i / frames)  # walks left -> right
        cv2.rectangle(frame, (x, 60), (x + 20, 150), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_pipeline_records_visits(app, tmp_path, monkeypatch):
    video = tmp_path / "walk.avi"
    make_video(video)
    monkeypatch.setattr(vp, "create_detector", lambda *a, **k: BlobDetector())
    monkeypatch.setattr(vp, "create_tracker", lambda *a, **k: CentroidTracker())
    monkeypatch.setattr(vp, "FLUSH_INTERVAL", 0.5)
    app.config["INFERENCE_EVERY_N_FRAMES"] = 1

    camera = Camera(name="Test", source=str(video), width=320, height=180)
    from app.extensions import db
    db.session.add(camera)
    db.session.commit()

    proc = vp.camera_manager.start(app, camera, Zone.query.all())
    # The blob walks through the "Books" zone (~2.3 s) and out of it; wait for that visit to be stored.
    deadline = time.time() + 20
    while time.time() < deadline and Visit.query.count() == 0:
        time.sleep(0.3)
        db.session.expire_all()
    stats = proc.stats()
    assert proc.latest_jpeg() is not None
    vp.camera_manager.stop(camera.id)

    assert stats["detector"] == "test-blob"
    assert stats["total_detected"] >= 1
    assert TrafficSample.query.count() > 0
    assert HeatmapCell.query.count() > 0
    visit = Visit.query.first()
    assert visit is not None
    assert visit.zone.name == "Books"
    assert 1.5 <= visit.dwell_seconds <= 4  # real-time pacing of the video file


def test_recording_writes_video_file(app, tmp_path, monkeypatch):
    from app.extensions import db
    from app.models import Setting

    video = tmp_path / "walk.avi"
    make_video(video, frames=60)
    monkeypatch.setattr(vp, "create_detector", lambda *a, **k: BlobDetector())
    monkeypatch.setattr(vp, "create_tracker", lambda *a, **k: CentroidTracker())
    Setting.put("enable_recording", "true")
    Setting.put("recording_path", str(tmp_path / "rec"))
    db.session.commit()
    camera = Camera(name="Rec", source=str(video))
    db.session.add(camera)
    db.session.commit()

    proc = vp.camera_manager.start(app, camera, [])
    time.sleep(1.5)
    vp.camera_manager.stop(camera.id)
    files = list((tmp_path / "rec").glob("camera*.avi"))
    assert len(files) == 1 and files[0].stat().st_size > 0


def test_bad_source_reports_error(app):
    from app.extensions import db
    camera = Camera(name="Missing", source="does-not-exist.mp4")
    db.session.add(camera)
    db.session.commit()
    proc = vp.VideoProcessor(app, camera.id, camera.source, [])
    proc._run()  # run synchronously
    assert proc.error and "Could not open" in proc.error
