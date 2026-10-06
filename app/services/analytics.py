"""Read-side analytics: everything the dashboard pages and the REST API show."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import HeatmapCell, TrafficSample, Visit, Zone

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DWELL_BUCKETS = [(0, 2, "0-2m"), (2, 5, "2-5m"), (5, 10, "5-10m"), (10, 15, "10-15m"),
                 (15, 20, "15-20m"), (20, 30, "20-30m"), (30, None, "30m+")]


# ---------------------------------------------------------------- helpers
def fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return "0s"
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s" if m else f"{s}s"


def pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def period_range(period: str = "today", start: str | None = None, end: str | None = None,
                 now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    today = datetime.combine(now.date(), time.min)
    if start and end:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end) + timedelta(days=1)
        return (s, e) if s < e else (e - timedelta(days=1), s + timedelta(days=1))
    if period == "week":
        return today - timedelta(days=6), today + timedelta(days=1)
    if period == "month":
        return today - timedelta(days=29), today + timedelta(days=1)
    if period == "year":
        return today - timedelta(days=364), today + timedelta(days=1)
    return today, today + timedelta(days=1)


def _visits(start: datetime, end: datetime):
    return Visit.query.filter(Visit.entered_at >= start, Visit.entered_at < end)


def _entries_total(start: datetime, end: datetime) -> int:
    total = db.session.query(func.coalesce(func.sum(TrafficSample.entries), 0)).filter(
        TrafficSample.timestamp >= start, TrafficSample.timestamp < end).scalar()
    return int(total or 0)


def _avg_dwell(start: datetime, end: datetime) -> float:
    value = db.session.query(func.avg(Visit.dwell_seconds)).filter(
        Visit.entered_at >= start, Visit.entered_at < end).scalar()
    return float(value or 0)


def _hourly_entries(start: datetime, end: datetime) -> dict[int, int]:
    rows = db.session.query(TrafficSample.timestamp, TrafficSample.entries).filter(
        TrafficSample.timestamp >= start, TrafficSample.timestamp < end).all()
    by_hour: dict[int, int] = defaultdict(int)
    for ts, entries in rows:
        if entries:  # hours with no arrivals (store closed) are not opening hours
            by_hour[ts.hour] += entries
    return by_hour


def is_service_zone(name: str) -> bool:
    """Checkout is a pass-through area, so it is left out of "hot zone" rankings."""
    return name.strip().lower() == "checkout"


def zone_visit_counts(start: datetime, end: datetime) -> dict[str, int]:
    rows = db.session.query(Zone.name, func.count(Visit.id)).outerjoin(
        Visit, (Visit.zone_id == Zone.id) & (Visit.entered_at >= start) & (Visit.entered_at < end)
    ).group_by(Zone.id).order_by(Zone.id).all()
    return {name: count for name, count in rows}


def current_visitors() -> int:
    from ..ai.video_processor import camera_manager

    running = [camera_manager.get(cid) for cid in camera_manager.running_ids()]
    if running:
        return sum(p.current_count for p in running)
    recent = TrafficSample.query.filter(
        TrafficSample.timestamp >= datetime.now() - timedelta(minutes=10)
    ).order_by(TrafficSample.timestamp.desc()).first()
    return recent.people_count if recent else 0


# ---------------------------------------------------------------- dashboard
def dashboard_summary(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start, end = period_range("today", now=now)
    yesterday = (start - timedelta(days=1), start)
    week_ago_start = start - timedelta(days=7)

    today_traffic = _entries_total(start, end)
    avg_daily_week = _entries_total(week_ago_start, start) / 7
    avg_dwell = _avg_dwell(start, end)
    last_week_dwell = _avg_dwell(week_ago_start, start)

    zone_counts = {z: c for z, c in zone_visit_counts(start, end).items() if not is_service_zone(z)}
    total_zone_visits = sum(zone_counts.values()) or 1
    hot = [z for z, c in zone_counts.items() if c / total_zone_visits >= 0.25]
    top_zone = max(zone_counts, key=zone_counts.get) if zone_counts else None

    visitors = current_visitors()
    yesterday_same_time = TrafficSample.query.filter(
        TrafficSample.timestamp >= yesterday[0], TrafficSample.timestamp <= now - timedelta(days=1)
    ).order_by(TrafficSample.timestamp.desc()).first()

    return {
        "current_visitors": visitors,
        "current_visitors_change": pct_change(visitors, yesterday_same_time.people_count)
        if visitors and yesterday_same_time else None,
        "today_traffic": today_traffic,
        "today_traffic_change": pct_change(today_traffic, avg_daily_week),
        "avg_dwell": fmt_duration(avg_dwell),
        "avg_dwell_seconds": round(avg_dwell, 1),
        "avg_dwell_change": pct_change(avg_dwell, last_week_dwell),
        "hot_zones": len(hot),
        "hot_zone_names": hot,
        "top_zone": top_zone,
        "top_zone_share": round(zone_counts.get(top_zone, 0) / total_zone_visits * 100) if top_zone else 0,
    }


def live_zone_occupancy() -> dict[str, int]:
    """People currently inside each zone (from open/very recent visits)."""
    cutoff = datetime.now() - timedelta(minutes=2)
    rows = db.session.query(Zone.name, func.count(Visit.id)).join(Visit).filter(
        Visit.exited_at >= cutoff).group_by(Zone.name).all()
    return {name: count for name, count in rows}


# ---------------------------------------------------------------- traffic
def traffic_trend(start: datetime, end: datetime) -> dict:
    days = (end - start).days
    rows = db.session.query(TrafficSample.timestamp, TrafficSample.entries).filter(
        TrafficSample.timestamp >= start, TrafficSample.timestamp < end).all()
    if days <= 1:
        buckets = defaultdict(int)
        for ts, e in rows:
            if e:
                buckets[ts.hour] += e
        hours = sorted(buckets) or list(range(9, 22))
        hours = list(range(min(hours), max(hours) + 1))
        return {"labels": [_hour_label(h) for h in hours], "values": [buckets.get(h, 0) for h in hours]}
    if days <= 62:
        buckets = defaultdict(int)
        for ts, e in rows:
            buckets[ts.date()] += e
        dates = [start.date() + timedelta(days=i) for i in range(days)]
        return {"labels": [d.strftime("%b %d") for d in dates], "values": [buckets.get(d, 0) for d in dates]}
    buckets = defaultdict(int)
    for ts, e in rows:
        buckets[(ts.year, ts.month)] += e
    months, cursor = [], date(start.year, start.month, 1)
    while cursor < end.date():
        months.append((cursor.year, cursor.month))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return {"labels": [date(y, m, 1).strftime("%b %Y") for y, m in months],
            "values": [buckets.get(k, 0) for k in months]}


def _hour_label(h: int) -> str:
    return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"


def traffic_summary(start: datetime, end: datetime) -> dict:
    span = end - start
    prev_start, prev_end = start - span, start
    total = _entries_total(start, end)
    prev_total = _entries_total(prev_start, prev_end)

    hourly = _hourly_entries(start, end)
    open_hours = len([h for h, v in hourly.items() if v]) * max(span.days, 1) or 1
    peak_hour = max(hourly, key=hourly.get) if hourly else None
    prev_hourly = _hourly_entries(prev_start, prev_end)

    n_days = max(span.days, 1)
    hours = sorted(hourly) or list(range(9, 22))
    distribution = {"labels": [_hour_label(h) for h in hours],
                    "values": [round(hourly.get(h, 0) / n_days, 1) for h in hours]}

    week_start = end - timedelta(days=7)
    weekday = defaultdict(int)
    for ts, e in db.session.query(TrafficSample.timestamp, TrafficSample.entries).filter(
            TrafficSample.timestamp >= week_start, TrafficSample.timestamp < end):
        weekday[ts.weekday()] += e

    visits = _visits(start, end).all()
    prev_visits = _visits(prev_start, prev_end).all()

    def engaged(vs):
        return round(sum(1 for v in vs if v.dwell_seconds >= 60) / len(vs) * 100, 1) if vs else 0

    avg_dwell, prev_avg_dwell = _avg_dwell(start, end), _avg_dwell(prev_start, prev_end)
    peak_val = max(hourly.values()) / n_days if hourly else 0
    prev_peak_val = max(prev_hourly.values()) / n_days if prev_hourly else 0

    # Share of tracked visitors who went on to enter at least one zone.
    zone_visitors = len({v.track_id for v in visits})
    entry_rate = round(min(zone_visitors / total * 100, 100)) if total else 0

    comparison = [
        {"metric": "Total Visitors", "current": f"{total:,}", "previous": f"{prev_total:,}",
         "change": pct_change(total, prev_total)},
        {"metric": "Peak Hour Traffic", "current": f"{peak_val:.0f} visitors", "previous": f"{prev_peak_val:.0f} visitors",
         "change": pct_change(peak_val, prev_peak_val)},
        {"metric": "Average Dwell Time", "current": fmt_duration(avg_dwell), "previous": fmt_duration(prev_avg_dwell),
         "change": pct_change(avg_dwell, prev_avg_dwell)},
        {"metric": "Engaged Visits (>1 min)", "current": f"{engaged(visits)}%", "previous": f"{engaged(prev_visits)}%",
         "change": pct_change(engaged(visits), engaged(prev_visits))},
    ]

    insights = []
    if peak_hour is not None:
        busiest_day = WEEKDAYS[max(weekday, key=weekday.get)] if weekday else "—"
        insights.append({"icon": "fa-trophy", "title": "Peak Performance",
                         "text": f"{_hour_label(peak_hour)} is the busiest hour and {busiest_day} the busiest day. "
                                 f"Consider staffing accordingly."})
    change = pct_change(total, prev_total)
    if change is not None:
        insights.append({"icon": "fa-chart-line", "title": "Growth Trend" if change >= 0 else "Traffic Decline",
                         "text": f"Traffic {'increased' if change >= 0 else 'decreased'} {abs(change)}% "
                                 f"compared with the previous period."})
    if hourly:
        quiet = min(hourly, key=hourly.get)
        avg_h = sum(hourly.values()) / len(hourly)
        drop = round((1 - hourly[quiet] / avg_h) * 100) if avg_h else 0
        insights.append({"icon": "fa-triangle-exclamation", "title": "Low Traffic Alert",
                         "text": f"{_hour_label(quiet)} sees {drop}% less traffic than average. "
                                 f"Opportunity for special promotions."})

    return {
        "kpis": {
            "total_visitors": total, "total_change": pct_change(total, prev_total),
            "avg_per_hour": round(total / open_hours) if total else 0,
            "avg_per_hour_change": pct_change(total / open_hours, prev_total / open_hours),
            "peak_hour": _hour_label(peak_hour) if peak_hour is not None else "—",
            "entry_rate": entry_rate,
        },
        "trend": traffic_trend(start, end),
        "hourly": distribution,
        "weekly": {"labels": WEEKDAYS, "values": [weekday.get(i, 0) for i in range(7)]},
        "comparison": comparison,
        "insights": insights,
    }


# ---------------------------------------------------------------- heatmap
HEAT_LEVELS = [(200, "very-hot", "Very Hot (200+)"), (150, "hot", "Hot (150-199)"),
               (100, "warm", "Warm (100-149)"), (50, "cool", "Cool (50-99)"), (0, "cold", "Cold (0-49)")]


def heat_level(count: int, days: int = 1) -> str:
    per_day = count / max(days, 1)
    for threshold, key, _ in HEAT_LEVELS:
        if per_day >= threshold:
            return key
    return "cold"


def heatmap_summary(start: datetime, end: datetime, mode: str = "visits") -> dict:
    days = max((end - start).days, 1)
    zones = Zone.query.order_by(Zone.id).all()
    visits = _visits(start, end).all()
    by_zone: dict[int, list[float]] = defaultdict(list)
    for v in visits:
        by_zone[v.zone_id].append(v.dwell_seconds)

    total = sum(len(v) for v in by_zone.values()) or 1
    zone_data = []
    for z in zones:
        dwells = by_zone.get(z.id, [])
        value = len(dwells) if mode == "visits" else round(sum(dwells) / len(dwells) / 60, 1) if dwells else 0
        zone_data.append({**z.to_dict(), "visits": len(dwells), "value": value,
                          "share": round(len(dwells) / total * 100), "shop_share": None,
                          "avg_dwell": fmt_duration(sum(dwells) / len(dwells)) if dwells else "0s",
                          "level": heat_level(len(dwells), days)})

    cells = db.session.query(HeatmapCell.gx, HeatmapCell.gy, func.sum(HeatmapCell.hits)).filter(
        HeatmapCell.day >= start.date(), HeatmapCell.day < end.date()
    ).group_by(HeatmapCell.gx, HeatmapCell.gy).all()

    insights = []
    if visits:
        shopping = [z for z in zone_data if not is_service_zone(z["name"])] or zone_data
        ranked = sorted(shopping, key=lambda z: z["visits"], reverse=True)
        shopping_total = sum(z["visits"] for z in shopping) or 1
        for z in shopping:
            z["shop_share"] = round(z["visits"] / shopping_total * 100)
        hottest, coldest = ranked[0], ranked[-1]
        insights.append({"icon": "fa-fire", "color": "danger", "title": f"Hottest Zone: {hottest['name']}",
                         "text": f"{hottest['name']} receives {hottest['shop_share']}% of shopping-zone visits. "
                                 f"Consider expanding this area or adding complementary products."})
        insights.append({"icon": "fa-snowflake", "color": "info", "title": f"Underutilized Area: {coldest['name']}",
                         "text": f"{coldest['name']} has the lowest traffic ({coldest['shop_share']}%). "
                                 f"Recommend repositioning near the entrance or adding promotional signage."})
        paths = _common_path(visits)
        if paths:
            path, share = paths
            insights.append({"icon": "fa-route", "color": "warning", "title": "Traffic Flow Pattern",
                             "text": f"{' → '.join(path)} is the most common path ({share}% of multi-zone visitors)."})
        shop_visits = [v for v in visits if v.zone and not is_service_zone(v.zone.name)]
        afternoon = Counter(v.zone.name for v in shop_visits if 14 <= v.entered_at.hour < 17)
        morning = Counter(v.zone.name for v in shop_visits if v.entered_at.hour < 12)
        if afternoon and morning:
            insights.append({"icon": "fa-clock", "color": "primary", "title": "Peak Hours Impact",
                             "text": f"Afternoons (2-5 PM) are led by {afternoon.most_common(1)[0][0]}; "
                                     f"mornings favour {morning.most_common(1)[0][0]}."})

    return {"zones": zone_data, "levels": [{"key": k, "label": label} for _, k, label in HEAT_LEVELS],
            "grid": [{"x": gx, "y": gy, "v": int(v)} for gx, gy, v in cells], "insights": insights}


def _common_path(visits) -> tuple[list[str], int] | None:
    by_track = defaultdict(list)
    for v in sorted(visits, key=lambda v: v.entered_at):
        if v.zone and (not by_track[v.track_id] or by_track[v.track_id][-1] != v.zone.name):
            by_track[v.track_id].append(v.zone.name)
    paths = Counter(tuple(p[:3]) for p in by_track.values() if len(p) >= 2)
    if not paths:
        return None
    path, count = paths.most_common(1)[0]
    return list(path), round(count / sum(paths.values()) * 100)


# ---------------------------------------------------------------- dwell
ZONE_ICONS = {"Electronics": "fa-tv", "Clothing": "fa-shirt", "Food & Drinks": "fa-utensils",
              "Books": "fa-book", "Checkout": "fa-cash-register"}


def _engagement(avg_seconds: float, name: str) -> str:
    if name.lower() == "checkout":
        return "N/A"
    minutes = avg_seconds / 60
    for limit, label in [(16, "Very High"), (14, "High"), (10, "Medium-High"), (5, "Medium")]:
        if minutes >= limit:
            return label
    return "Low"


def dwell_summary(start: datetime, end: datetime) -> dict:
    span = end - start
    visits = _visits(start, end).all()
    prev = [v.dwell_seconds for v in _visits(start - span, start).all()]
    dwells = [v.dwell_seconds for v in visits]

    by_zone: dict[str, list[float]] = defaultdict(list)
    for v in visits:
        if v.zone:
            by_zone[v.zone.name].append(v.dwell_seconds)

    zones = []
    for z in Zone.query.order_by(Zone.id).all():
        d = by_zone.get(z.name, [])
        avg = sum(d) / len(d) if d else 0
        zones.append({"name": z.name, "color": z.color, "icon": ZONE_ICONS.get(z.name, "fa-store"),
                      "visits": len(d), "avg_seconds": avg, "avg": fmt_duration(avg),
                      "median": fmt_duration(statistics.median(d)) if d else "0s",
                      "max": fmt_duration(max(d)) if d else "0s", "engagement": _engagement(avg, z.name)})

    active = [z for z in zones if z["visits"]]
    longest = max(active, key=lambda z: z["avg_seconds"]) if active else None
    shortest = min(active, key=lambda z: z["avg_seconds"]) if active else None

    buckets = [0] * len(DWELL_BUCKETS)
    for d in dwells:
        m = d / 60
        for i, (lo, hi, _) in enumerate(DWELL_BUCKETS):
            if m >= lo and (hi is None or m < hi):
                buckets[i] += 1
                break

    trend_end = end
    trend_start = trend_end - timedelta(days=7)
    daily = defaultdict(list)
    for v in _visits(trend_start, trend_end).all():
        daily[v.entered_at.date()].append(v.dwell_seconds)
    trend_days = [trend_start.date() + timedelta(days=i) for i in range(7)]

    recs = []
    for z in sorted(active, key=lambda z: z["avg_seconds"], reverse=True):
        if z["name"].lower() == "checkout":
            recs.append({"icon": "fa-gauge-high", "title": "Optimize Checkout Speed",
                         "text": f"Average checkout time is {z['avg']}. Consider adding self-checkout "
                                 f"stations during peak hours to reduce wait times."})
        elif z is longest:
            recs.append({"icon": "fa-arrow-up", "title": f"Increase {z['name']} Engagement",
                         "text": f"{z['name']} has the highest dwell time ({z['avg']}). Add interactive "
                                 f"displays or demo stations to convert browsing into purchases."})
        elif z["avg_seconds"] < 6 * 60:
            recs.append({"icon": "fa-bullseye", "title": f"{z['name']} Promotions",
                         "text": f"Low dwell time ({z['avg']}) suggests quick decisions. Add promotional "
                                 f"displays at the entrance to increase impulse purchases."})

    avg_all = sum(dwells) / len(dwells) if dwells else 0
    med_all = statistics.median(dwells) if dwells else 0
    return {
        "kpis": {
            "average": fmt_duration(avg_all), "average_change": pct_change(avg_all, sum(prev) / len(prev) if prev else 0),
            "median": fmt_duration(med_all), "median_change": pct_change(med_all, statistics.median(prev) if prev else 0),
            "longest_zone": longest["name"] if longest else "—", "longest_avg": longest["avg"] if longest else "",
            "shortest_zone": shortest["name"] if shortest else "—", "shortest_avg": shortest["avg"] if shortest else "",
        },
        "distribution": {"labels": [b[2] for b in DWELL_BUCKETS], "values": buckets},
        "by_zone": {"labels": [z["name"] for z in zones], "values": [z["visits"] for z in zones],
                    "colors": [z["color"] for z in zones]},
        "trend": {"labels": [WEEKDAYS[d.weekday()] for d in trend_days],
                  "values": [round(sum(daily[d]) / len(daily[d]) / 60, 1) if daily[d] else 0 for d in trend_days]},
        "zones": zones,
        "recommendations": recs,
    }
