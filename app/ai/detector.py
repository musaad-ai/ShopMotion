"""Person detection.

``YoloDetector`` (Ultralytics YOLOv8) is the primary backend. When the
``ultralytics`` package or its weights are unavailable the system falls back to
OpenCV's built-in HOG people detector so the app still runs on any machine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def ltwh(self):
        return [self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1]


class YoloDetector:
    name = "yolov8"
    PERSON_CLASS = 0

    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.5):
        from ultralytics import YOLO  # imported lazily: heavy dependency

        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> list[Detection]:
        result = self.model.predict(
            frame, classes=[self.PERSON_CLASS], conf=self.confidence, verbose=False
        )[0]
        detections = []
        for box, conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
            detections.append(Detection(*box, confidence=float(conf)))
        return detections


class HogDetector:
    name = "opencv-hog"

    def __init__(self, confidence: float = 0.5):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        scale = 640 / w if w > 640 else 1.0
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
        rects, weights = self.hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        detections = []
        for (x, y, rw, rh), weight in zip(rects, np.ravel(weights) if len(rects) else []):
            # HOG SVM scores are unbounded; squash them into 0-1 to share one threshold.
            conf = float(1 / (1 + np.exp(-weight)))
            if conf >= self.confidence:
                detections.append(Detection(x / scale, y / scale, (x + rw) / scale, (y + rh) / scale, conf))
        return detections


def create_detector(backend: str = "auto", model_path: str = "yolov8n.pt", confidence: float = 0.5):
    if backend in ("auto", "yolo"):
        try:
            detector = YoloDetector(model_path, confidence)
            log.info("Using YOLOv8 detector (%s)", model_path)
            return detector
        except Exception as exc:  # missing package, weights or GPU problems
            if backend == "yolo":
                raise
            log.warning("YOLOv8 unavailable (%s); falling back to OpenCV HOG", exc)
    return HogDetector(confidence)
