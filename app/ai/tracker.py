"""Multi-object tracking.

``DeepSortTracker`` wraps ``deep-sort-realtime`` (appearance + motion
association). ``CentroidTracker`` is a dependency-free fallback that matches
detections to existing tracks by IoU and centroid distance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .detector import Detection

log = logging.getLogger(__name__)


@dataclass
class Track:
    track_id: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def foot_point(self):
        """Bottom-centre of the box: where the person stands on the floor."""
        return (self.x1 + self.x2) / 2, self.y2

    @property
    def center(self):
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


class CentroidTracker:
    name = "centroid-iou"

    def __init__(self, max_missed: int = 15, max_distance: float = 120.0):
        self.max_missed = max_missed
        self.max_distance = max_distance
        self._next_id = 1
        self._tracks: dict[int, dict] = {}  # id -> {"box": [...], "missed": int}

    def update(self, detections: list[Detection], frame=None) -> list[Track]:
        boxes = [[d.x1, d.y1, d.x2, d.y2] for d in detections]
        track_ids = list(self._tracks)
        unmatched = set(range(len(boxes)))
        matched_tracks = set()

        if track_ids and boxes:
            # Score every (track, detection) pair; greedily take the best matches.
            pairs = []
            for t_idx, tid in enumerate(track_ids):
                tbox = self._tracks[tid]["box"]
                tc = np.array([(tbox[0] + tbox[2]) / 2, (tbox[1] + tbox[3]) / 2])
                for d_idx, dbox in enumerate(boxes):
                    dc = np.array([(dbox[0] + dbox[2]) / 2, (dbox[1] + dbox[3]) / 2])
                    dist = float(np.linalg.norm(tc - dc))
                    overlap = iou(tbox, dbox)
                    if overlap > 0.1 or dist < self.max_distance:
                        pairs.append((overlap - dist / 1000.0, tid, d_idx))
            for _, tid, d_idx in sorted(pairs, reverse=True):
                if tid in matched_tracks or d_idx not in unmatched:
                    continue
                self._tracks[tid] = {"box": boxes[d_idx], "missed": 0}
                matched_tracks.add(tid)
                unmatched.discard(d_idx)

        for tid in track_ids:
            if tid not in matched_tracks:
                self._tracks[tid]["missed"] += 1
                if self._tracks[tid]["missed"] > self.max_missed:
                    del self._tracks[tid]

        for d_idx in sorted(unmatched):
            self._tracks[self._next_id] = {"box": boxes[d_idx], "missed": 0}
            self._next_id += 1

        return [Track(str(tid), *t["box"]) for tid, t in self._tracks.items() if t["missed"] == 0]


class DeepSortTracker:
    name = "deepsort"

    def __init__(self, max_age: int = 30):
        from deep_sort_realtime.deepsort_tracker import DeepSort

        self.tracker = DeepSort(max_age=max_age, n_init=2, embedder="mobilenet", half=False)

    def update(self, detections: list[Detection], frame=None) -> list[Track]:
        raw = [(d.ltwh, d.confidence, "person") for d in detections]
        tracks = self.tracker.update_tracks(raw, frame=frame)
        out = []
        for t in tracks:
            if not t.is_confirmed() or t.time_since_update > 0:
                continue
            x1, y1, x2, y2 = t.to_ltrb()
            out.append(Track(str(t.track_id), x1, y1, x2, y2))
        return out


def create_tracker(backend: str = "auto"):
    if backend in ("auto", "deepsort"):
        try:
            tracker = DeepSortTracker()
            log.info("Using DeepSORT tracker")
            return tracker
        except Exception as exc:
            if backend == "deepsort":
                raise
            log.warning("DeepSORT unavailable (%s); falling back to centroid tracker", exc)
    return CentroidTracker()
