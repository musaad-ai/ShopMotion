"""Analytics REST endpoints consumed by the dashboard charts."""
from flask import jsonify, request
from flask_login import login_required

from ..services import analytics
from . import api_bp


def _range():
    return analytics.period_range(request.args.get("period", "today"),
                                  request.args.get("start"), request.args.get("end"))


@api_bp.get("/analytics/summary")
@login_required
def analytics_summary():
    return jsonify(analytics.dashboard_summary())


@api_bp.get("/analytics/traffic")
@login_required
def analytics_traffic():
    try:
        start, end = _range()
    except ValueError:
        return jsonify(error="Invalid date range"), 400
    return jsonify(analytics.traffic_summary(start, end))


@api_bp.get("/analytics/trend")
@login_required
def analytics_trend():
    start, end = _range()
    return jsonify(analytics.traffic_trend(start, end))


@api_bp.get("/analytics/heatmap")
@login_required
def analytics_heatmap():
    start, end = _range()
    mode = request.args.get("mode", "visits")
    return jsonify(analytics.heatmap_summary(start, end, mode))


@api_bp.get("/analytics/dwell")
@login_required
def analytics_dwell():
    start, end = _range()
    return jsonify(analytics.dwell_summary(start, end))


@api_bp.get("/analytics/zones")
@login_required
def analytics_zones():
    start, end = _range()
    return jsonify(visits=analytics.zone_visit_counts(start, end),
                   live=analytics.live_zone_occupancy())
