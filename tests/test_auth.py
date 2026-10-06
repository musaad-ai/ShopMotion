from app.models import User
from tests.conftest import login


def test_dashboard_requires_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_api_requires_login(client):
    assert client.get("/api/analytics/summary").status_code in (302, 401)


def test_login_and_logout(client):
    res = login(client, "viewer")
    assert b"Dashboard Overview" in res.data
    res = client.post("/logout", follow_redirects=True)
    assert b"signed out" in res.data


def test_wrong_password(client):
    res = client.post("/login", data={"username": "viewer", "password": "nope"}, follow_redirects=True)
    assert b"Invalid username or password" in res.data


def test_passwords_are_hashed(app):
    user = User.query.filter_by(username="viewer").first()
    assert user.password_hash != "password123"
    assert user.check_password("password123")


def test_register_creates_viewer(client, app):
    res = client.post("/register", data={"username": "newbie", "email": "newbie@example.com",
                                         "password": "longpassword", "confirm": "longpassword"},
                      follow_redirects=True)
    assert b"Account created" in res.data
    assert User.query.filter_by(username="newbie").first().role == "viewer"


def test_open_redirect_is_blocked(client):
    res = client.post("/login?next=https://evil.example", data={"username": "viewer", "password": "password123"})
    assert res.headers["Location"] == "/"


def test_viewer_cannot_open_admin_pages(viewer_client):
    for url in ("/settings", "/cameras", "/store-layout", "/admin/users"):
        assert viewer_client.get(url).status_code == 403
    assert viewer_client.post("/api/system/settings", json={"detection_confidence": 0.7}).status_code == 403


def test_admin_can_open_admin_pages(admin_client):
    for url in ("/settings", "/cameras", "/store-layout", "/admin/users"):
        assert admin_client.get(url).status_code == 200
