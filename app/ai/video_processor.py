"""Camera capture + analysis pipeline.

Camera -> VideoProcessor -> Detector -> Tracker -> BehaviorAnalyzer -> Database

Each running camera gets one background thread. The latest annotated frame is
kept in memory for the MJPEG stream; aggregated results are written to the
database every few seconds inside the Flask app context.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .behavior import BehaviorAnalyzer, ZoneRect
from .detector import create_detector
from .tracker import create_tracker

log = logging.getLogger(__name__)

FLUSH_INTERVAL = 5.0  # seconds between database writes


def parse_source(source: str):
    """Numeric strings are device indexes; anything else is a path or stream URL."""
    return int(source) if str(source).strip().isdigit() else source


class VideoProcessor:
    def __init__(self, app, camera_id: int, source: str, zones: list[ZoneRect],
                 width: int = 1280, height: int = 720):
        self.app = app
        self.camera_id = camera_id
        self.source = source
        self.width, self.height = width, height
        cfg = app.config
        with app.app_context():
            from ..models import Setting
            confidence = float(Setting.get("detection_confidence"))
            self.tracking_enabled = Setting.get("enable_tracking") == "true"
            self.crowd_threshold = int(Setting.get("crowd_threshold"))
            self.recording_enabled = Setting.get("enable_recording") == "true"
            self.recording_dir = Path(Setting.get("recording_path") or "recordings/")
        if not self.recording_dir.is_absolute():
            self.recording_dir = Path(cfg["RECORDING_ROOT"]) / self.recording_dir
        self.detector = create_detector(cfg["DETECTOR_BACKEND"], cfg["YOLO_MODEL"], confidence)
        self.tracker = create_tracker(cfg["TRACKER_BACKEND"])
        self.analyzer = BehaviorAnalyzer(zones, grid=cfg["HEATMAP_GRID"])
        self.every_n = max(1, cfg["INFERENCE_EVERY_N_FRAMES"])
        self.jpeg_quality = cfg["STREAM_JPEG_QUALITY"]

        self.current_count = 0
        self.fps = 0.0
        self.error: str | None = None
        self.started_at: datetime | None = None
        self.detection_log: deque = deque(maxlen=50)
        self._frame_jpeg: bytes | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._crowd_alerted = False
        self._writer: cv2.VideoWriter | None = None

    # ---- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.error = None
        self.started_at = datetime.now()
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.camera_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    # ---- frame access ----------------------------------------------------
    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._frame_jpeg

    def snapshot(self, directory: Path) -> Path | None:
        data = self.latest_jpeg()
        if data is None:
            return None
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"camera{self.camera_id}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        path.write_bytes(data)
        return path

    def stats(self) -> dict:
        now = datetime.now()
        return {
            "running": self.running,
            "error": self.error,
            "current_visitors": self.current_count,
            "total_detected": self.analyzer.total_detected,
            "peak_count": self.analyzer.peak_count,
            "avg_dwell_seconds": round(self.analyzer.current_dwell_average(now), 1),
            "fps": round(self.fps, 1),
            "detector": self.detector.name,
            "tracker": self.tracker.name if self.tracking_enabled else "disabled",
        }

    # ---- main loop -------------------------------------------------------
    def _run(self) -> None:
        cap = cv2.VideoCapture(parse_source(self.source))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened():
            self.error = f"Could not open camera source '{self.source}'"
            log.error(self.error)
            return

        # Video files are read faster than real time; pace them at their native
        # FPS so measured dwell times match what happened in the footage.
        is_file = isinstance(parse_source(self.source), str) and not str(self.source).lower().startswith(("rtsp", "http"))
        frame_interval = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 25) if is_file else 0.0

        frame_idx, last_flush, fps_t0, fps_frames = 0, time.time(), time.time(), 0
        tracks = []
        try:
            while not self._stop.is_set():
                frame_started = time.time()
                ok, frame = cap.read()
                if not ok:
                    if is_file:  # loop the footage
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    self.error = "Camera stopped delivering frames"
                    break

                if frame_idx % self.every_n == 0:
                    tracks = self._analyse(frame)
                annotated = self._annotate(frame, tracks)
                self._publish(annotated)
                if self.recording_enabled:
                    self._record(annotated, cap)
                frame_idx += 1

                fps_frames += 1
                if time.time() - fps_t0 >= 1.0:
                    self.fps = fps_frames / (time.time() - fps_t0)
                    fps_t0, fps_frames = time.time(), 0
                if time.time() - last_flush >= FLUSH_INTERVAL:
                    self._flush()
                    last_flush = time.time()
                if frame_interval:
                    remaining = frame_interval - (time.time() - frame_started)
                    if remaining > 0:
                        time.sleep(remaining)
        except Exception as exc:  # keep the web app alive if the pipeline dies
            log.exception("Video pipeline crashed")
            self.error = str(exc)
        finally:
            cap.release()
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            self._flush(close_all=True)
            self.current_count = 0

    def _analyse(self, frame: np.ndarray):
        from .tracker import Track

        detections = self.detector.detect(frame)
        if self.tracking_enabled:
            tracks = self.tracker.update(detections, frame)
        else:  # count-only mode: no identities, so no dwell time
            tracks = [Track(f"d{i}", d.x1, d.y1, d.x2, d.y2) for i, d in enumerate(detections)]
        h, w = frame.shape[:2]
        if self.tracking_enabled:
            self.analyzer.update(tracks, w, h, datetime.now())
        if len(tracks) != self.current_count and tracks:
            self.detection_log.appendleft({
                "time": datetime.now().strftime("%H:%M:%S"),
                "count": len(tracks),
                "message": f"{len(tracks)} person(s) detected in frame",
            })
        self.current_count = len(tracks)
        return tracks

    def _annotate(self, frame: np.ndarray, tracks) -> np.ndarray:
        h, w = frame.shape[:2]
        for zone in self.analyzer.zones:
            x1, y1 = int(zone.x * w), int(zone.y * h)
            x2, y2 = int((zone.x + zone.w) * w), int((zone.y + zone.h) * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (234, 126, 102), 1)
            cv2.putText(frame, zone.name, (x1 + 4, y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (234, 126, 102), 1)
        for t in tracks:
            p1, p2 = (int(t.x1), int(t.y1)), (int(t.x2), int(t.y2))
            cv2.rectangle(frame, p1, p2, (80, 200, 120), 2)
            cv2.putText(frame, f"ID {t.track_id}", (p1[0], max(p1[1] - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 200, 120), 2)
        cv2.putText(frame, f"People: {len(tracks)}  FPS: {self.fps:.1f}", (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def _record(self, frame: np.ndarray, cap) -> None:
        """Opt-in recording of the annotated feed (Settings -> Recording)."""
        if self._writer is None:
            self.recording_dir.mkdir(parents=True, exist_ok=True)
            path = self.recording_dir / f"camera{self.camera_id}_{datetime.now():%Y%m%d_%H%M%S}.avi"
            h, w = frame.shape[:2]
            fps = cap.get(cv2.CAP_PROP_FPS) or 15
            self._writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
            log.info("Recording camera %s to %s", self.camera_id, path)
        self._writer.write(frame)

    def _publish(self, frame: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if ok:
            with self._lock:
                self._frame_jpeg = buf.tobytes()

    def _flush(self, close_all: bool = False) -> None:
        visits, heat, new_ids = self.analyzer.flush(datetime.now(), close_all=close_all)
        try:
            with self.app.app_context():
                from ..services.ingest import store_batch
                store_batch(self.camera_id, self.current_count, new_ids, visits, heat)
                self._check_crowd()
        except Exception:
            log.exception("Failed to store analytics batch")

    def _check_crowd(self) -> None:
        from ..extensions import db
        from ..models import Activity, Alert

        if self.current_count >= self.crowd_threshold and not self._crowd_alerted:
            message = f"{self.current_count} people in view of camera {self.camera_id}"
            db.session.add(Alert(level="warning", icon="fa-users", title="High traffic detected", message=message))
            db.session.add(Activity(kind="warning", icon="fa-triangle-exclamation",
                                    title="Zone congestion detected",
                                    message=f"{self.current_count} visitors on camera {self.camera_id}"))
            db.session.commit()
            self._crowd_alerted = True
            from ..services.notify import send_alert_email
            send_alert_email(self.app, "High traffic detected", message)
        elif self.current_count < self.crowd_threshold * 0.7:
            self._crowd_alerted = False


class CameraManager:
    """Registry of running processors, one per camera."""

    def __init__(self):
        self._processors: dict[int, VideoProcessor] = {}
        self._lock = threading.Lock()

    def get(self, camera_id: int) -> VideoProcessor | None:
        return self._processors.get(camera_id)

    def start(self, app, camera, zones) -> VideoProcessor:
        with self._lock:
            proc = self._processors.get(camera.id)
            if proc is None or not proc.running:
                rects = [ZoneRect(z.id, z.name, z.x, z.y, z.w, z.h) for z in zones]
                proc = VideoProcessor(app, camera.id, camera.source, rects, camera.width, camera.height)
                self._processors[camera.id] = proc
            proc.start()
            return proc

    def stop(self, camera_id: int) -> None:
        with self._lock:
            proc = self._processors.pop(camera_id, None)
        if proc:
            proc.stop()

    def stop_all(self) -> None:
        for camera_id in list(self._processors):
            self.stop(camera_id)

    def running_ids(self) -> list[int]:
        return [cid for cid, p in self._processors.items() if p.running]


camera_manager = CameraManager()
