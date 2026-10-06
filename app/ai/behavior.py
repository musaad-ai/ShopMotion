"""Behaviour analysis: zone visits, dwell time and heatmap accumulation.

Pure Python with no Flask or database dependency, so it is easy to unit test.
The ``VideoProcessor`` feeds it tracks every processed frame and periodically
drains the finished visits and heatmap hits into the database.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .tracker import Track


@dataclass
class ZoneRect:
    id: int
    name: str
    x: float
    y: float
    w: float
    h: float

    def contains(self, nx: float, ny: float) -> bool:
        return self.x <= nx <= self.x + self.w and self.y <= ny <= self.y + self.h


@dataclass
class FinishedVisit:
    track_id: str
    zone_id: int
    entered_at: datetime
    exited_at: datetime

    @property
    def dwell_seconds(self) -> float:
        return (self.exited_at - self.entered_at).total_seconds()


@dataclass
class _TrackState:
    zone_id: int | None
    entered_at: datetime
    last_seen: datetime


@dataclass
class BehaviorAnalyzer:
    zones: list[ZoneRect]
    grid: tuple[int, int] = (32, 18)
    lost_after: timedelta = timedelta(seconds=3)
    min_dwell: float = 1.0  # ignore visits shorter than this (people walking past)

    _states: dict[str, _TrackState] = field(default_factory=dict)
    _finished: list[FinishedVisit] = field(default_factory=list)
    _heat: dict[tuple[int, int], int] = field(default_factory=lambda: defaultdict(int))
    _seen_ids: set[str] = field(default_factory=set)
    _new_ids: int = 0
    total_detected: int = 0
    peak_count: int = 0

    def zone_for(self, nx: float, ny: float) -> int | None:
        for zone in self.zones:
            if zone.contains(nx, ny):
                return zone.id
        return None

    def update(self, tracks: list[Track], frame_w: int, frame_h: int, now: datetime) -> None:
        self.peak_count = max(self.peak_count, len(tracks))
        gx_max, gy_max = self.grid
        for track in tracks:
            fx, fy = track.foot_point
            nx = min(max(fx / frame_w, 0.0), 1.0)
            ny = min(max(fy / frame_h, 0.0), 1.0)
            self._heat[(min(int(nx * gx_max), gx_max - 1), min(int(ny * gy_max), gy_max - 1))] += 1

            if track.track_id not in self._seen_ids:
                self._seen_ids.add(track.track_id)
                self._new_ids += 1
                self.total_detected += 1

            zone_id = self.zone_for(nx, ny)
            state = self._states.get(track.track_id)
            if state is None:
                self._states[track.track_id] = _TrackState(zone_id, now, now)
                continue
            if state.zone_id != zone_id:
                self._close(track.track_id, state, now)
                self._states[track.track_id] = _TrackState(zone_id, now, now)
            else:
                state.last_seen = now

        # Tracks that disappeared long enough are considered gone.
        for track_id, state in list(self._states.items()):
            if now - state.last_seen > self.lost_after:
                self._close(track_id, state, state.last_seen)
                del self._states[track_id]

    def _close(self, track_id: str, state: _TrackState, exited_at: datetime) -> None:
        if state.zone_id is None:
            return
        visit = FinishedVisit(track_id, state.zone_id, state.entered_at, exited_at)
        if visit.dwell_seconds >= self.min_dwell:
            self._finished.append(visit)

    def current_dwell_average(self, now: datetime) -> float:
        """Mean time-in-zone of everyone currently inside a zone (seconds)."""
        durations = [(now - s.entered_at).total_seconds() for s in self._states.values() if s.zone_id]
        return sum(durations) / len(durations) if durations else 0.0

    def flush(self, now: datetime | None = None, close_all: bool = False):
        """Return (finished visits, heatmap hits, new visitor count) and reset buffers."""
        if close_all:
            for track_id, state in list(self._states.items()):
                self._close(track_id, state, now or state.last_seen)
            self._states.clear()
        visits, self._finished = self._finished, []
        heat, self._heat = dict(self._heat), defaultdict(int)
        new_ids, self._new_ids = self._new_ids, 0
        return visits, heat, new_ids
