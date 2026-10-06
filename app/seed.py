"""Default store layout and a synthetic data generator for demos.

The generator simulates shoppers walking through the default five-zone store
so every dashboard page has realistic data without a camera attached.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, time, timedelta

from .extensions import db
from .models import (Activity, Alert, Camera, HeatmapCell, Report, Setting, TrafficSample,
                     User, Visit, Zone)

DEFAULT_ZONES = [
    # name, colour, x, y, w, h (normalised to the store floor / camera frame)
    ("Electronics", "#dc3545", 0.10, 0.15, 0.25, 0.30),
    ("Clothing", "#fd7e14", 0.65, 0.15, 0.25, 0.30),
    ("Food & Drinks", "#0d6efd", 0.65, 0.55, 0.25, 0.30),
    ("Books", "#20c997", 0.10, 0.55, 0.25, 0.30),
    ("Checkout", "#6f42c1", 0.40, 0.35, 0.20, 0.15),
]

# Relative popularity, mean dwell (minutes) and spread for each zone.
ZONE_PROFILE = {
    "Electronics": (0.28, 15.5, 6.0),
    "Clothing": (0.24, 12.0, 5.0),
    "Food & Drinks": (0.20, 4.5, 2.0),
    "Books": (0.12, 18.0, 7.0),
    "Checkout": (0.16, 2.3, 0.9),
}

# Visitors per hour, shaped like a typical retail day (store open 8 AM - 7 PM).
HOURLY_SHAPE = {8: 12, 9: 19, 10: 15, 11: 26, 12: 32, 13: 28, 14: 45, 15: 42, 16: 38, 17: 30, 18: 26}
WEEKDAY_FACTOR = [0.95, 1.1, 0.9, 1.0, 1.15, 1.3, 1.2]


def ensure_defaults() -> None:
    if Zone.query.count() == 0:
        for name, color, x, y, w, h in DEFAULT_ZONES:
            db.session.add(Zone(name=name, color=color, x=x, y=y, w=w, h=h))
    if Camera.query.count() == 0:
        db.session.add(Camera(name="Main Entrance", location="Store floor", source="0"))
    db.session.commit()


def _ensure_user(username: str, email: str, password: str, role: str) -> User:
    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    return user


def seed_demo_data(days: int = 30, reset: bool = True, seed: int = 42, now: datetime | None = None) -> dict:
    rng = random.Random(seed)
    now = now or datetime.now()
    ensure_defaults()
    admin = _ensure_user("admin", "admin@shopmotion.local", "admin123", "admin")
    viewer = _ensure_user("viewer", "viewer@shopmotion.local", "viewer123", "viewer")

    if reset:
        for model in (Visit, TrafficSample, HeatmapCell, Alert, Activity, Report):
            model.query.delete()
        db.session.commit()

    zones = {z.name: z for z in Zone.query.all()}
    camera = Camera.query.first()
    names = [n for n in ZONE_PROFILE if n in zones]
    weights = [ZONE_PROFILE[n][0] for n in names]
    grid_w, grid_h = 32, 18

    visits, samples, heat = [], [], {}
    visitor_seq = 0
    start_day = (now - timedelta(days=days - 1)).date()

    for d in range(days):
        day = start_day + timedelta(days=d)
        day_factor = WEEKDAY_FACTOR[day.weekday()] * rng.uniform(0.9, 1.1)
        for hour, base in HOURLY_SHAPE.items():
            hour_start = datetime.combine(day, time(hour))
            if hour_start > now:
                break
            arrivals = max(0, int(rng.gauss(base * day_factor, base * 0.12)))
            per_slot = [0] * 12  # 5-minute traffic samples
            for _ in range(arrivals):
                visitor_seq += 1
                track = f"demo-{visitor_seq}"
                t = hour_start + timedelta(seconds=rng.uniform(0, 3600))
                if t > now:
                    continue
                per_slot[min(int((t - hour_start).total_seconds() // 300), 11)] += 1
                # Each shopper visits 1-3 zones; most end at checkout.
                route = []
                for _ in range(rng.choice([1, 2, 2, 3])):
                    pick = rng.choices(names, weights=weights)[0]
                    if pick != "Checkout" and pick not in route:
                        route.append(pick)
                if rng.random() < 0.5:
                    route.append("Checkout")
                for zone_name in route:
                    _, mean, spread = ZONE_PROFILE[zone_name]
                    dwell = max(20.0, rng.gauss(mean, spread) * 60)
                    exit_t = t + timedelta(seconds=dwell)
                    z = zones[zone_name]
                    visits.append(Visit(track_id=track, zone_id=z.id, camera_id=camera.id,
                                        entered_at=t, exited_at=exit_t, dwell_seconds=round(dwell, 1)))
                    # Presence in the zone's grid cells, proportional to dwell.
                    for _ in range(max(1, int(dwell // 60))):
                        gx = int((z.x + rng.random() * z.w) * grid_w)
                        gy = int((z.y + rng.random() * z.h) * grid_h)
                        key = (day, min(gx, grid_w - 1), min(gy, grid_h - 1))
                        heat[key] = heat.get(key, 0) + 1
                    t = exit_t + timedelta(seconds=rng.uniform(10, 60))
            occupancy = max(1, int(base * day_factor * 0.35))
            for slot, entries in enumerate(per_slot):
                ts = hour_start + timedelta(minutes=5 * slot)
                if ts > now:
                    break
                samples.append(TrafficSample(timestamp=ts, camera_id=camera.id, entries=entries,
                                             people_count=max(0, occupancy + rng.randint(-3, 3))))

    # A "right now" snapshot so the live widgets have something to show in a demo.
    in_store = rng.randint(18, 26)
    samples.append(TrafficSample(timestamp=now - timedelta(seconds=30), camera_id=camera.id,
                                 people_count=in_store, entries=0))
    for i in range(in_store):
        zone_name = rng.choices(names, weights=weights)[0]
        entered = now - timedelta(seconds=rng.uniform(30, 600))
        visits.append(Visit(track_id=f"demo-live-{i}", zone_id=zones[zone_name].id, camera_id=camera.id,
                            entered_at=entered, exited_at=now,
                            dwell_seconds=round((now - entered).total_seconds(), 1)))

    db.session.add_all(visits)
    db.session.add_all(samples)
    db.session.add_all(HeatmapCell(day=k[0], gx=k[1], gy=k[2], hits=v) for k, v in heat.items())

    m = lambda minutes: now - timedelta(minutes=minutes)  # noqa: E731
    db.session.add_all([
        Alert(level="warning", icon="fa-users", title="High Traffic in Electronics",
              message="Visitor density above threshold", created_at=m(2)),
        Alert(level="info", icon="fa-circle-info", title="System Update Available",
              message="ShopMotion 1.1 is available", created_at=m(60)),
        Alert(level="danger", icon="fa-camera", title="Camera 3 Offline",
              message="No frames received for 5 minutes", created_at=m(180)),
        Activity(kind="success", icon="fa-user-plus", title="Peak hour reached",
                 message="Store traffic reached daily peak with 47 visitors", created_at=m(5)),
        Activity(kind="info", icon="fa-chart-area", title="Analytics report generated",
                 message="Weekly analytics report has been automatically generated", created_at=m(60)),
        Activity(kind="warning", icon="fa-triangle-exclamation", title="Zone congestion detected",
                 message="Electronics section showing high visitor density", created_at=m(120)),
        Activity(kind="success", icon="fa-video", title="All cameras online",
                 message="Every configured camera is streaming normally", created_at=m(240)),
    ])
    for key, value in Setting.DEFAULTS.items():
        Setting.put(key, value)
    db.session.commit()

    from .services.reports import generate_report
    generate_report("traffic", "week", viewer)
    generate_report("heatmap", "month", viewer)
    Activity.query.filter_by(title="Analytics report generated").filter(Activity.created_at > m(1)).delete()
    db.session.commit()

    return {"visits": len(visits), "traffic_samples": len(samples), "heatmap_cells": len(heat),
            "users": User.query.count(), "admin": admin.username}
