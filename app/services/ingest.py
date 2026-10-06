"""Persist batches produced by the video pipeline."""
from __future__ import annotations

from datetime import datetime

from ..extensions import db
from ..models import HeatmapCell, TrafficSample, Visit


def store_batch(camera_id: int, people_count: int, new_visitors: int, visits, heat: dict) -> None:
    now = datetime.now()
    db.session.add(TrafficSample(timestamp=now, camera_id=camera_id,
                                 people_count=people_count, entries=new_visitors))
    for v in visits:
        db.session.add(Visit(track_id=f"{camera_id}-{v.track_id}", zone_id=v.zone_id, camera_id=camera_id,
                             entered_at=v.entered_at, exited_at=v.exited_at, dwell_seconds=v.dwell_seconds))
    if heat:
        today = now.date()
        existing = {(c.gx, c.gy): c for c in HeatmapCell.query.filter_by(day=today).all()}
        for (gx, gy), hits in heat.items():
            cell = existing.get((gx, gy))
            if cell is None:
                db.session.add(HeatmapCell(day=today, gx=gx, gy=gy, hits=hits))
            else:
                cell.hits += hits
    db.session.commit()
