"""Report generation and CSV export."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from ..extensions import db
from ..models import Activity, Report
from . import analytics

REPORT_TYPES = {
    "traffic": "Traffic Report",
    "heatmap": "Heatmap Analysis",
    "dwell": "Dwell Time Report",
    "summary": "Store Performance Summary",
}
PERIOD_NAMES = {"today": "Daily", "week": "Weekly", "month": "Monthly", "year": "Yearly"}


def build_report_data(report_type: str, start: datetime, end: datetime) -> dict:
    if report_type == "traffic":
        return analytics.traffic_summary(start, end)
    if report_type == "heatmap":
        return analytics.heatmap_summary(start, end)
    if report_type == "dwell":
        return analytics.dwell_summary(start, end)
    return {
        "traffic": analytics.traffic_summary(start, end),
        "heatmap": analytics.heatmap_summary(start, end),
        "dwell": analytics.dwell_summary(start, end),
    }


def generate_report(report_type: str, period: str, user, start: str | None = None, end: str | None = None) -> Report:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report type '{report_type}'")
    s, e = analytics.period_range(period, start, end)
    prefix = PERIOD_NAMES.get(period, "Custom") if not (start and end) else "Custom"
    report = Report(
        title=f"{prefix} {REPORT_TYPES[report_type]}", report_type=report_type,
        period_start=s, period_end=e, data_json=json.dumps(build_report_data(report_type, s, e)),
        created_by=user.id if user else None,
    )
    db.session.add(report)
    db.session.add(Activity(kind="info", icon="fa-chart-area", title="Analytics report generated",
                            message=f"{report.title} was generated"))
    db.session.commit()
    return report


def report_to_csv(report: Report) -> str:
    data = json.loads(report.data_json)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ShopMotion report", report.title])
    writer.writerow(["Period", f"{report.period_start:%Y-%m-%d}", f"{report.period_last_day:%Y-%m-%d}"])
    writer.writerow([])
    sections = data if report.report_type == "summary" else {report.report_type: data}
    for name, section in sections.items():
        writer.writerow([name.upper()])
        if "kpis" in section:
            for key, value in section["kpis"].items():
                writer.writerow([key, value])
        for series_key in ("trend", "hourly", "weekly", "distribution"):
            series = section.get(series_key)
            if series:
                writer.writerow([])
                writer.writerow([series_key] + series["labels"])
                writer.writerow(["value"] + series["values"])
        if "zones" in section:
            writer.writerow([])
            rows = section["zones"]
            keys = [k for k in rows[0] if k not in ("color", "x", "y", "w", "h", "icon")] if rows else []
            writer.writerow(keys)
            for row in rows:
                writer.writerow([row[k] for k in keys])
        writer.writerow([])
    return out.getvalue()
