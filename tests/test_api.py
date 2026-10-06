from datetime import datetime

import pytest

from app.models import Report, Setting, Zone
from app.seed import seed_demo_data


@pytest.fixture()
def seeded(app):
    seed_demo_data(days=10, now=datetime.now())
    return app


PAGES = ["/", "/live", "/analytics/traffic", "/analytics/heatmap", "/analytics/dwell", "/reports"]


def test_all_pages_render(seeded, admin_client):
    for url in PAGES:
        assert admin_client.get(url).status_code == 200, url


@pytest.mark.parametrize("period", ["today", "week", "month", "year"])
def test_analytics_endpoints(seeded, viewer_client, period):
    traffic = viewer_client.get(f"/api/analytics/traffic?period={period}").get_json()
    assert traffic["kpis"]["total_visitors"] > 0
    assert len(traffic["trend"]["labels"]) == len(traffic["trend"]["values"])
    heat = viewer_client.get(f"/api/analytics/heatmap?period={period}").get_json()
    assert {z["name"] for z in heat["zones"]} == {"Electronics", "Clothing", "Food & Drinks", "Books", "Checkout"}
    dwell = viewer_client.get(f"/api/analytics/dwell?period={period}").get_json()
    assert sum(dwell["distribution"]["values"]) > 0


def test_custom_date_range(seeded, viewer_client):
    res = viewer_client.get("/api/analytics/traffic?start=2020-01-01&end=2020-01-07")
    assert res.status_code == 200
    assert res.get_json()["kpis"]["total_visitors"] == 0


def test_live_detect_without_camera(viewer_client):
    data = viewer_client.get("/api/live/detect").get_json()
    assert data["running"] is False


def test_settings_validation(admin_client):
    assert admin_client.post("/api/system/settings", json={"detection_confidence": 5}).status_code == 400
    res = admin_client.post("/api/system/settings", json={"detection_confidence": 0.7, "enable_tracking": False})
    assert res.status_code == 200
    assert Setting.get("detection_confidence") == "0.70"
    assert Setting.get("enable_tracking") == "false"
    admin_client.post("/api/system/settings/reset")
    assert Setting.get("detection_confidence") == "0.5"


def test_camera_crud(admin_client):
    created = admin_client.post("/api/system/cameras", json={"name": "Aisle 3", "source": "video.mp4",
                                                             "resolution": "640x480", "fps": 15}).get_json()
    assert created["resolution"] == "640x480"
    updated = admin_client.put(f"/api/system/cameras/{created['id']}", json={"name": "Aisle 4"}).get_json()
    assert updated["name"] == "Aisle 4"
    assert admin_client.delete(f"/api/system/cameras/{created['id']}").status_code == 200


def test_save_zones_replaces_layout(admin_client):
    zones = admin_client.get("/api/system/zones").get_json()
    zones = zones[:2] + [{"name": "Toys", "color": "#123456", "x": 0.4, "y": 0.7, "w": 0.2, "h": 0.2}]
    saved = admin_client.put("/api/system/zones", json=zones).get_json()
    assert [z["name"] for z in saved] == ["Electronics", "Clothing", "Toys"]
    assert Zone.query.count() == 3


def test_generate_view_download_and_delete_report(seeded, viewer_client):
    res = viewer_client.post("/api/reports", json={"type": "summary", "period": "week"})
    assert res.status_code == 201
    report_id = res.get_json()["id"]
    assert viewer_client.get(f"/reports/{report_id}").status_code == 200
    csv = viewer_client.get(f"/reports/{report_id}/download")
    assert csv.mimetype == "text/csv" and b"TRAFFIC" in csv.data
    assert viewer_client.delete(f"/api/reports/{report_id}").status_code == 200
    assert Report.query.get(report_id) is None


def test_alert_resolve(seeded, viewer_client):
    alerts = viewer_client.get("/api/system/alerts").get_json()
    assert alerts
    viewer_client.post(f"/api/system/alerts/{alerts[0]['id']}/resolve")
    assert len(viewer_client.get("/api/system/alerts").get_json()) == len(alerts) - 1
